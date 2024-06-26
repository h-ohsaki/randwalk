#!/usr/bin/env python3
#
#
# Copyright (c) 2023, Hiroyuki Ohsaki.
# All rights reserved.
#

from functools import lru_cache
import collections
import math
import random
import statistics

from perlcompat import die, warn, getopts
import graph_tools
import numpy

EPS = 1e-4
GRAPH_TYPES = 'random,ba,barandm,ring,tree,btree,lattice,voronoi,db,3-regular,4-regular,limaini'
AGENT_TYPES = 'EmbedRW,SRW,SARW,HybridRW,BloomRW,kHistory_LRU,kHistory_FIFO,kHistory,VARW,NBRW,BiasedRW,EigenvecRW,ClosenessRW,BetweennessRW,EccentricityRW,LZRW,MaxDegreeRW,MERW,OBRW'

# ----------------------------------------------------------------
def conf95(vals):
    """Return 95% confidence interval for measurements VALS."""
    zval = 1.960
    if len(vals) <= 1:
        return 0
    return zval * statistics.stdev(vals) / math.sqrt(len(vals))

def mean_and_conf95(vals):
    """Return the mean and the 95% confience interval for measurements
    VALS."""
    return statistics.mean(vals), conf95(vals)

def _create_graph(type_, n=100, k=3.):
    """Randomly generate a graph instance using network generation model TYPE_.
    If possible, a graph with N vertices and the average degree of K is
    generated."""
    m = int(n * k / 2)
    g = graph_tools.Graph(directed=False)
    g.set_graph_attribute('name', type_)
    if type_ == 'random':
        return g.create_random_graph(n, m)
    if type_ == 'ba':
        return g.create_graph('ba', n, 10, int(k))
    if type_ == 'barandm':
        return g.create_graph('barandom', n, m)
    if type_ == 'ring':
        return g.create_graph('ring', n)
    if type_ == 'tree':
        return g.create_graph('tree', n)
    if type_ == 'btree':
        return g.create_graph('btree', n)
    if type_ == 'lattice':
        return g.create_graph('lattice', 2, int(math.sqrt(n)))
    if type_ == 'voronoi':
        return g.create_graph('voronoi', n // 2)
    if type_ == 'db':
        # NOTE: average degree must be divisable by 2.
        return g.create_graph('db', n, n * 2)
    if type_ == '3-regular':
        return g.create_random_regular_graph(n, 3)
    if type_ == '4-regular':
        return g.create_random_regular_graph(n, 4)
    if type_ == 'limaini':
        # NOTE: 5 clusters, 5% of vertices in each cluster, other vertices are
        # added with preferential attachment.
        return g.create_graph('li_maini', int(n * .75), 5, int(n * .25 / 5))
    # FIXMME: Support treeba, general_ba, and latent.
    die(f"Invalid graph type `{type_}'.\nSupported graph types: {GRAPH_TYPES}."
        )

def create_graph(type_, *kargs, **kwargs):
    g = _create_graph(type_, *kargs, **kwargs)
    # Anonymize vertex names.
    h = g.anonymize_graph()
    h.set_graph_attribute('name', type_)
    return h

def create_agent(type_, *args, **kwargs):
    # Create an agent of a given agent class.
    cls = eval(type_)
    return cls(*args, **kwargs)

def random_with_distrib(distrib):
    total = sum(distrib.values())
    chosen = random.uniform(0, total)
    cumul = 0
    for key, weight in distrib.items():
        if cumul <= chosen < cumul + weight:
            return key
        cumul += weight
    return key

# ----------------------------------------------------------------
# NOTE: The follwing code is essentially based on
# https://stackoverflow.com/questions/9026519/bloomfilter-python .
class BloomFilter:
    """Bloom filter of size SIZE with three types of hash functions."""
    def __init__(self, size):
        if size is None:
            size = 1000
            size = 32 * 3
        self.size = size  # Size of the Bloom filter in bits.
        self.bitarray = [0] * self.size

    def hashes(self, key):
        """Return three independent hashes in [0 : self.size] for KEY."""
        digest = hash(str(key))
        hash1 = digest % self.size
        hash2 = (digest // self.size) % self.size
        hash3 = (digest // self.size // self.size) % self.size
        return hash1, hash2, hash3

    def add(self, key):
        """Register KEY to the Bloom filter."""
        for n in self.hashes(key):
            self.bitarray[n] = 1

    def query(self, key):
        """Check if KEY already exists in the Bloom filter.  Note that the
        Bloom filter may result in false positive but not in false
        negative."""
        return all(self.bitarray[n] == 1 for n in self.hashes(key))

# ----------------------------------------------------------------
class SRW:
    """Simple Random Walk (SRW) agent."""
    def __init__(self,
                 graph=None,
                 current=None,
                 target=None,
                 *kargs,
                 **kwargs):
        self.graph = graph
        self.path = []  # List of visited vertiecs.
        self.step = 0  # Global clock.
        self.nvisits = collections.defaultdict(
            int)  # Records the number of vists.
        self.ncovered = 0  # The number of uniquely visisted vertices.
        self.hitting = collections.defaultdict(
            int)  # Records the first visiting time.
        self.current = None
        if current:
            self.move_to(current)
        self.target = target

    def __repr__(self):
        return f'{self.name()}(step={self.step}, current={self.current}, ncovered={self.ncovered})'

    def name(self):
        return type(self).__name__

    def weight(self, u, v):
        """Transistion weight form vertex U to vertex V."""
        # Every neighbor is chosen with the same probability.
        return 1

    def pick_next(self, u=None):
        """Randomly choose one of neighbors of vetex U with the probabiity
        proportional to its weight."""
        if u is None:
            u = self.current
        neighbors = self.graph.neighbors(u)
        # Vertex U must not be isolated.
        assert neighbors
        # Save all weights for transistion from vertex U.
        weights = {v: self.weight(u, v) for v in neighbors}
        return random_with_distrib(weights)

    def move_to(self, v):
        """Move the random walker to vertex V."""
        self.current = v
        self.path.append(v)
        if not self.nvisits[v]:  # is this the first time?
            self.hitting[v] = self.step
            self.ncovered += 1
        self.nvisits[v] += 1

    def advance(self):
        """Advance the random walker one step forward."""
        v = self.pick_next()
        self.move_to(v)
        self.step += 1

    def prev_vertex(self, n=1):
        try:
            return self.path[-(n + 1)]
        except IndexError:
            return None

    def dump(self):
        v = self.current
        d = self.graph.degree(v)
        print(f'{self.step}\tvisit\t{v}\t{self.nvisits[v]}\t{d}')
        print(
            f'{self.step}\tstatus\t{self.ncovered}\t{self.graph.nvertices()}')

# ----------------------------------------------------------------
class BiasedRW(SRW):
    """Biased Random Walk (Biased-RW) agent."""
    def __init__(self, alpha=-.5, *kargs, **kwargs):
        self.alpha = alpha
        super().__init__(*kargs, **kwargs)

    def weight(self, u, v):
        """Biased RW randomlyh chooses one of its neighbor with the
        probability proportional to d_v^alpha where d_v is the degree of
        vertex V and alpha is a control parameter."""
        if u is None:
            u = self.current
        w = super().weight(u, v)
        dv = self.graph.degree(v)
        return w * dv**self.alpha

class NBRW(BiasedRW):
    """Non-Backtracking Random Walk (NBRW) agent."""
    def weight(self, u, v):
        if u is None:
            u = self.current
        # This code assumes that vertex U is the current vetex.
        assert u == self.current
        if v == self.prev_vertex():
            return EPS
        else:
            return super().weight(u, v)

class SARW(BiasedRW):
    """Self-Avoiding Random Walk (SARW) agent."""
    def weight(self, u, v):
        """SARW is equivalent to SRW except that the agent tries to avoid to
        re-visit vertices that the agent has already visited."""
        if u is None:
            u = self.current
        if self.nvisits[v]:
            return EPS
        else:
            return super().weight(u, v)

class BloomRW(BiasedRW):
    """Random Walk with Bloom filter (Bloom-RW) agent."""
    def __init__(self, bf_size=None, *kargs, **kwargs):
        self.bf = BloomFilter(size=bf_size)
        super().__init__(*kargs, **kwargs)

    def weight(self, u, v):
        if u is None:
            u = self.current
        if self.bf.query(v):
            if v not in self.path:
                warn(f'** false positive {v}')
            return EPS
        else:
            return super().weight(u, v)

    def move_to(self, v):
        super().move_to(v)
        self.bf.add(v)

class VARW(NBRW):
    """Random Walk with Vicinity Avoidance (VARW) agent."""
    def weight(self, u, v):
        """VARW tries to avoid vicinity (i.e., neighbor vertices of the
        previously-visited vertices)."""
        if u is None:
            u = self.current
        # This code assumes that vertex U is the current vetex.
        assert u == self.current
        # NOTE: the original VA-RW avoids neighbors of the last K vertices, rather
        # than those of the previous one.
        t = self.prev_vertex()
        if t and self.graph.has_edge(t, v):
            return EPS
        else:
            return super().weight(u, v)

# ----------------------------------------------------------------
class LZRW(BiasedRW):
    """Lazy Random Walk (LZRW) agent."""
    def __init__(self, laziness=.5, *kargs, **kwargs):
        self.laziness = laziness
        super().__init__(*kargs, **kwargs)

    def pick_next(self, u=None):
        """LZRW probabilistically stays at the current vertex."""
        if u is None:
            u = self.current
        if random.random() <= self.laziness:
            return u
        else:
            return super().pick_next(u)

class MaxDegreeRW(LZRW):
    """Max-Degree Random Walk (MaxDegreeRW) agent."""
    def __init__(self, *kargs, **kwargs):
        super().__init__(*kargs, **kwargs)
        # FIXME: This code assumes that the graph is static.
        self.max_degree = max(
            [self.graph.degree(v) for v in self.graph.vertices()])

    def pick_next(self, u=None):
        # Stay at the current vertex with the probability of
        # (max_degree - degree)/degree.
        degree = self.graph.degree(self.current)
        self.laziness = (self.max_degree - degree) / self.max_degree
        return super().pick_next(u)

class HybridRW(BloomRW):
    """Hybrid Random Walk (HybridRW) agent."""
    def weight(self, u, v):
        if u is None:
            u = self.current
        # This code assumes that vertex U is the current vetex.
        assert u == self.current
        # NBRW-like behavior.
        if v == self.prev_vertex():
            return EPS
        # VARW-like behavior.
        # NOTE: the original VA-RW avoids neighbors of the last K vertices, rather
        # than those of the previous one.
        t = self.prev_vertex()
        if t and self.graph.has_edge(t, v):
            return EPS
        # BloomRW-like behavior.
        if self.bf.query(v):
            return EPS
        # BiasedRW-like behavior.
        dv = self.graph.degree(v)
        return dv**self.alpha

class kHistory(BiasedRW):
    """k-History Random Walk (kHistoryRW) agent."""
    def __init__(self, hist_size=3, *kargs, **kwargs):
        self.hist_size = hist_size
        self.history = collections.deque(maxlen=hist_size)
        super().__init__(*kargs, **kwargs)

    def weight(self, u, v):
        if v in self.history:
            return EPS
        else:
            return super().weight(u, v)

    def move_to(self, v):
        # Always place the recent entry at the top.
        # NOTE: The history might have duplicates.
        self.history.append(self.current)
        super().move_to(v)

class kHistory_FIFO(kHistory):
    """k-History Random Walk with FIFO replacement (kHistoryRW-FIFO) agent."""
    def move_to(self, v):
        if self.current not in self.history:
            # The oldest entry is flushed automatically.
            self.history.append(self.current)
        # FIXME: Avoid hard-coding.
        super(BiasedRW, self).move_to(v)

class kHistory_LRU(kHistory):
    """k-History Random Walk with LRU replacement (kHistoryRW-LRU) agent."""
    def move_to(self, v):
        # Always place the recent entry at the top.
        if self.current in self.history:
            self.history.remove(self.current)
        self.history.append(self.current)
        # FIXME: Avoid hard-coding.
        super(BiasedRW, self).move_to(v)

# ----------------------------------------------------------------
class EigenvecRW(BiasedRW):
    """Eigenvector Random Walk (EigenvecRW) agent."""
    def __init__(self, *kargs, **kwargs):
        super().__init__(*kargs, **kwargs)
        # Precompute centrality scores of all vertices.
        self.centrality_cache = {}
        for v in self.graph.vertices():
            self.centrality_cache[v] = self.centrality(v)

    def centrality(self, v):
        return self.graph.eigenvector_centrality(v)

    def weight(self, u, v):
        if u is None:
            u = self.current
        c = self.centrality_cache[v] + EPS
        return c**self.alpha

class ClosenessRW(EigenvecRW):
    """Closeness Random Walk (ClosenessRW) agent."""
    def centrality(self, v):
        return self.graph.closeness_centrality(v)

class BetweennessRW(EigenvecRW):
    """Betweenness Random Walk (BetweennessRW) agent."""
    def centrality(self, v):
        return self.graph.betweenness_centrality(v)

class EccentricityRW(EigenvecRW):
    """Eccentricity Random Walk (EccentricityRW) agent."""
    def centrality(self, v):
        return self.graph.eccentricity(v)

# ----------------------------------------------------------------
class MERW(SRW):
    """Maximal-Entropy Random Walk (MERW) agent."""
    def __init__(self, *kargs, **kwargs):
        super().__init__(*kargs, **kwargs)
        adj = self.graph.adjacency_matrix()
        eigvals, eigvecs = numpy.linalg.eig(adj)
        # Find the index of the largest eigenvalue.
        i = max(enumerate(eigvals), key=lambda x: x[1])[0]
        self.eigval1 = eigvals[i]
        self.eigvec1 = eigvecs[:, i]
        # Alaways use positive eigenvector.  The signs of all elements must
        # be the same.
        if self.eigvec1[0] < 0:
            self.eigvec1 = -self.eigvec1

    def weight(self, u, v):
        if u is None:
            u = self.current
        return (1 / self.eigval1) * (self.eigvec1[v - 1] / self.eigvec1[u - 1])

class EmbedRW(SRW):
    def __init__(self, *kargs, **kwargs):
        super().__init__(*kargs, **kwargs)
        # Target node is mandatory.
        if self.target is None:
            self.target = self.graph.random_vertex()
        self.target_embed = self.embed_vector(self.target)

    @lru_cache
    def embed_vector(self, v):
        vec = self.graph.node2vec(v)
        norm = numpy.linalg.norm(vec)
        return vec / norm

    @lru_cache
    def _weight(self, u, v):
        e_v = self.embed_vector(v)
        # Only use the embedding vector of a neighbor node in seach mode.
        norm1 = numpy.linalg.norm(self.target_embed - e_v, ord=1)
        # NOTE: the transistion probability must be high for a small norm.
        return norm1

    @lru_cache
    def weight(self, u, v):
        if u is None:
            u = self.current
        # Normalize the weight among all neighbor nodes.
        weights = [self._weight(u, _) for _ in self.graph.neighbors(u)]
        total = EPS + sum(weights)
        w = 1 - self._weight(u, v) / total
        # print(f'{u}->{v}\t{w}')
        return w

class SparseEmbedRW(EmbedRW):
    def __init__(self, embed_ratio=.1, *kargs, **kwargs):
        super().__init__(*kargs, **kwargs)
        self.embed_ratio = embed_ratio
        self.last_embed_vector = self.embed_vector(self.current)

    @lru_cache
    def embed_vector(self, v):
        # Embedding vector is available only in the target node and a fraction of nodes.
        if v == self.target or random.random() <= self.embed_ratio:
            vec = self.graph.node2vec(v)
            norm = numpy.linalg.norm(vec)
            return vec / norm
        else:
            return None

    @lru_cache
    def _weight(self, u, v):
        e_v = self.embed_vector(v)
        # If the embedding vector is not available, use the last observed one.
        if e_v is None:
            e_v = self.last_embed_vector
        if e_v is None:
            return 1
        norm1 = numpy.linalg.norm(self.target_embed - e_v, ord=1)
        return norm1

    def advance(self):
        vec = self.embed_vector(self.current)
        if vec is not None:
            # Record the last observed embed vector.
            self.last_embed_vector = vec
        super().advance()

class LevyRW(BiasedRW):
    @lru_cache
    def weight(self, u, v):
        if u is None:
            u = self.current
        return self.graph.shortest_path_length(u, v)**-self.alpha

    def pick_next(self, u=None):
        """Randomly choose one of vetex with the probabiity
        proportional to its weight."""
        if u is None:
            u = self.current
        neighbors = [v for v in self.graph.vertices() if v != u]
        # Save all weights for transistion from vertex U.
        weights = {v: self.weight(u, v) for v in neighbors}
        return random_with_distrib(weights)

class SprintRW(LevyRW):
    def __init__(self, *kargs, **kwargs):
        super().__init__(*kargs, **kwargs)
        self.distant_nodes = self.pick_distant_nodes()
        self.next_distant_node = None

    def pick_distant_nodes(self):
        distant_nodes = {}
        for u in self.graph.vertices():
            # Randomly pick 3 non-local nodes.
            non_neighbors = [
                v for v in self.graph.vertices()
                if not self.graph.has_edge(u, v) and u != v
            ]
            distant_nodes[u] = random.sample(non_neighbors, 3)
        return distant_nodes

    def pick_next(self, u=None):
        if u is None:
            u = self.current
        # Is moving toward the distant node?
        if self.next_distant_node:
            return self.next_hop_to(u, self.next_distant_node)

        neighbors = self.graph.neighbors(u)
        # Save all weights for transistion from vertex U.
        # Pick the next destination from neighbors and distant nodes.
        weights = {
            v: self.weight(u, v)
            for v in set(neighbors) | set(self.distant_nodes[u])
        }
        v = random_with_distrib(weights)
        if v in neighbors:
            # Normal random walk.
            return v
        else:
            # Go to the chosen distant node following the shortest path.
            self.next_distant_node = v
            return self.next_hop_to(u, self.next_distant_node)

    def advance(self):
        super().advance()
        # Arrived at the distant node?
        if self.next_distant_node and self.current == self.next_distant_node:
            self.next_distant_node = None

    def next_hop_to(self, u, v):
        paths = list(self.graph.shortest_paths(u, v))
        path = random.choice(paths)
        # Next hop of the shortest path from vertex U to vertex V.
        return path[1]
