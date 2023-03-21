#!/usr/bin/env pypy3
#
# A sample program for randwalk module.
# Copyright (c) 2023, Hiroyuki Ohsaki.
# All rights reserved.
#
# $Id: run.py,v 1.6 2023/03/20 08:44:56 ohsaki Exp ohsaki $
#

import sys
import statistics

from perlcompat import die, warn, getopts
import randwalk
import graph_tools
import tbdump

def usage():
    die(f"""\
usage: {sys.argv[0]} [-v] [file...]
  -v    verbose mode
""")

def simulate(g, start_node, agent_cls, ntrials=100):
    n_nodes = len(g.vertices())
    covert_times = []
    hitting_times = []
    for n in range(ntrials):
        # Create an agent of a given agent class.
        cls = eval('randwalk.' + agent_cls)
        agent = cls(graph=g, current=start_node)
        # Perform an instance of simulation.
        while agent.ncovered < n_nodes:
            agent.advance()
        # Collect statistics.
        covert_time = agent.step
        covert_times.append(covert_time)
        _ = [agent.hitting[v] for v in g.vertices()]
        hitting_time = statistics.mean(_)
        hitting_times.append(hitting_time)
        # Calcurate averages of cover and hitting times.
        avg_cover = statistics.mean(covert_times)
        avg_hitting = statistics.mean(hitting_times)
        print(f'{agent_cls:8} {n:4} {avg_cover:8.2f} {avg_hitting:8.2f}\r',
              end='')
    print()

def main():
    n_nodes = 100
    kavg = 3.
    # Create graph.
    g = graph_tools.Graph(directed=False)
    g = g.create_graph('random', n_nodes, int(n_nodes * kavg / 2))
    # g = g.create_graph('barandom', n_nodes, int(n_nodes * kavg / 2))
    start_node = 1
    for agent in 'SRW SARW MixedRW BloomRW VARW LRVRW FIFORW NBRW BiasedRW'.split():
        simulate(g, start_node, agent)

if __name__ == "__main__":
    main()
