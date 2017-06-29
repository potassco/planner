#!/usr/bin/python


#
# IMPORTS
#

import clingo
import sys
import argparse
import re
from time import clock
import clingo_stats
import os

#
# LOGGING
#

outf        = 0
FORCE_PRINT = 1
PRINT       = 2
VERBOSE     = 3
log_level   = PRINT
def log(string,level=VERBOSE):
    if level > log_level: return
    if outf==1 and level != FORCE_PRINT:
        string = "% " + string.replace("\n","\n% ")
    sys.stdout.write(string + "\n")


#
# MEMORY USAGE (for Unix)
#
def memory_usage(key="VmSize"):

    # data
    proc_status = '/proc/%d/status' % os.getpid()
    scale = {'kB': 1024.0, 'mB': 1,
             'KB': 1024.0, 'MB': 1}

    # get pseudo file  /proc/<pid>/status
    try:
        t = open(proc_status)
        v = t.read()
        t.close()
    except:
        return -1  # non-Linux?

    # get key line e.g. 'VmSize:  9999  kB\n ...'
    i = v.index(key)
    v = v[i:].split(None, 3)  # whitespace
    if len(v) < 3:
        return -1  # invalid format?

    # return
    return int(float(v[1]) / scale[v[2]])




#
# SCHEDULERS
#


class Scheduler:


    def __init__(self):
        pass


    def next(self,result):
        return 0



class A_Scheduler(Scheduler):


    def __init__(self,start,inc,limit,size,propagate_unsat):
        self.__length          = start
        self.__inc             = inc
        self.__limit           = limit
        self.__size            = size
        self.__propagate_unsat = propagate_unsat
        self.__runs            = []
        self.__first           = True
        self.__nones           = 0


    def next(self,result):

        # START: add all runs
        if self.__first:
            self.__first  = False
            self.__runs   = [ self.__length+(i*self.__inc) for i in range(self.__size) ]
            self.__runs   = [ i for i in self.__runs if i<=self.__limit ]
            if len(self.__runs) > 0: self.__length = self.__runs[-1]
            self.__nones  = set()

        # NONE: check if all Nones, enqueue, and pop
        elif result is None:
            current_length = self.__runs[0]
            self.__nones.add(current_length)
            if len(self.__nones) == len(self.__runs): return None
            self.__runs.append(current_length)
            self.__runs = self.__runs[1:]

        # not NONE
        else:

            current_length = self.__runs[0]
            if current_length in self.__nones:
                self.__nones.remove(current_length)

            # UNKNOWN: enqueue and pop
            if result.unknown:
                self.__runs.append(current_length)

            # UNSAT
            else:
                if self.__propagate_unsat:                            # propagate unsat
                    self.__runs = [ i for i in self.__runs if i>=current_length ]
                next_length = self.__length + self.__inc
                if next_length <= self.__limit and not self.__nones:  # if inside the limit and mem: enqueue next
                    self.__length = next_length
                    self.__runs.append(self.__length)

            self.__runs = self.__runs[1:]                             # pop

        # log and return
        log("Queue:\t\t " + str(self.__runs))
        return self.__runs[0] if len(self.__runs)>0 else None



class Run:


    def __init__(self,index,length,effort,solve):
        self.index  = index
        self.length = length
        self.effort = effort
        self.solve  = solve


    def __repr__(self):
        return "("+",".join([str(i) for i in [self.index,self.length,self.effort,self.solve]])+")"



class B_Scheduler:


    def __init__(self,start,inc,limit,size,propagate_unsat,gamma):
        self.__index           = 0
        self.__start           = start
        self.__inc             = inc
        self.__limit           = limit
        self.__size            = size
        self.__propagate_unsat = propagate_unsat
        self.__gamma           = gamma
        self.__runs            = []
        self.__next_runs       = []
        self.__first           = True
        self.__nones           = set()


    def next(self,result):

        # if not first time
        if not self.__first:

            current = self.__runs[0]

            # NONE: append to __next_runs
            if result is None:
                self.__nones.add(current)
                self.__next_runs.append(current)

            # not NONE
            else:
                if current in self.__nones:
                    self.__nones.remove(current)
                # UNKNOWN: effort++, and append to __next_runs
                if result.unknown:
                    current.effort += 1
                    self.__next_runs.append(current)
                # UNSAT and propagate: reset __next_runs
                elif result.unsatisfiable and self.__propagate_unsat:
                    self.__next_runs = []

            # NONE, UNKNOWN or UNSAT: pop __runs
            self.__runs = self.__runs[1:]
            # move to __next_runs while not solve
            while self.__runs != [] and not self.__runs[0].solve:
                self.__next_runs.append(self.__runs[0])
                self.__runs = self.__runs[1:]

        self.__first = False

        # if no more runs
        if self.__runs == []:

            # if __next_runs is not empty: add to __runs
            if self.__next_runs != []:
                if len(self.__nones) == len(self.__next_runs): return None
                first = self.__next_runs[0]
                first.solve = True
                self.__runs = [ first ]
                for i in self.__next_runs[1:]:
                    i.solve = True if (i.effort < (((first.effort+1) * (self.__gamma ** (i.index - first.index)))+0.5)) else False
                    self.__runs.append(i)

            # else: add new to __runs
            else:
                self.__runs = [ Run(self.__index,self.__start+(self.__inc*self.__index),0,True) ]
                self.__index += 1
                first = self.__runs[0]
                if first.length > self.__limit: return None

            # reset __next_runs
            self.__next_runs = []

            # add next runs
            while (0.5 < ((first.effort+1) * (self.__gamma ** (self.__index - first.index)))) and not self.__nones:
                if len(self.__runs)>= self.__size: break
                next_length = self.__start+(self.__inc*self.__index)
                if next_length > self.__limit: break
                self.__runs.append(Run(self.__index,next_length,0,True))
                self.__index += 1

        # log and return
        log("Queue:\t\t " + str(self.__runs))
        return self.__runs[0].length



class C_Scheduler(Scheduler):


    def __init__(self,start,inc,limit,propagate_unsat):
        self.__length          = start
        self.__inc             = float(inc)
        self.__limit           = limit
        self.__propagate_unsat = propagate_unsat
        self.__runs            = []
        self.__first           = True
        self.__nones           = set()


    def next(self,result):

        # START: add first run
        if self.__first:
            self.__runs   = [ self.__length ]
            if self.__length == 0: self.__length = 1
            self.__first  = False

        # NONE: check if all Nones, append and pop
        elif result is None:
            self.__nones.add(self.__runs[0])
            if len(self.__nones) == len(self.__runs): return None
            self.__runs.append(self.__runs[0])
            self.__runs = self.__runs[1:]

        # ELSE: add new and handle last
        else:
            current_length = self.__runs[0]
            if current_length in self.__nones:
                self.__nones.remove(current_length)
            next_length = self.__length * self.__inc
            if int(next_length) == int(self.__length): next_length = self.__length + 1
            if int(next_length) <= self.__limit and not self.__nones:
                self.__runs.append(int(next_length))
                self.__length = next_length
            # UNKNOWN: append
            if result.unknown:
                self.__runs.append(current_length)
            # UNSAT: propagate_unsat
            elif self.__propagate_unsat:
                self.__runs = [ i for i in self.__runs if i>=current_length ]
            # pop
            self.__runs = self.__runs[1:]

        # log and return
        log("Queue:\t\t " + str(self.__runs))
        return self.__runs[0] if len(self.__runs)>0 else None



#
# SOLVER
#

BASE  = "base"
STEP  = "step"
CHECK = "check"
QUERY = "query"
SKIP  = "skip"
EXTERNALS_PROGRAM  = """
#program step(t).  #external skip(t).
#program check(t). #external query(t).
"""
FORBID_ACTIONS_PROGRAM = """
#program step(t).
:-     occurs(A,t),     skip(t). % no action
"""
FORCE_ACTIONS_PROGRAM = """
#program step(t).
:- not occurs(_,t), not skip(t). % some action
"""


class Solver:


    def __init__(self, ctl, options):

        self.__ctl         = ctl
        self.__length      = 0
        self.__last_length = 0
        self.__options     = options
        self.__verbose     = options['verbose']
        self.__result      = None
        if self.__verbose: self.__memory = memory_usage()

        # mem
        self.__mem         = True if options['check_mem'] else False
        self.__mem_limit   = options['check_mem']*0.9
        self.__mem_max     = 0
        self.__mem_before  = 0

        # set solving and restart policy
        self.__ctl.configuration.solve.solve_limit = "umax,"+str(options['restarts_per_solve'])
        if int(options['conflicts_per_restart']) != 0:
            self.__ctl.configuration.solver[0].restarts="F,"+str(options['conflicts_per_restart'])

        self.__move_query = options['move_query'] 


    def __on_model(self,m):
        if self.__options['outf'] == 0:
            log("Answer: 1\n" + str(m),PRINT)
        else:
            log("ANSWER\n" + " ".join([str(x)+"." for x in m.symbols(shown=True)]),FORCE_PRINT)


    def __verbose_start(self):
        self.__time0 = clock()


    def __verbose_end(self,string):
        log(string+" Time:\t {:.2f}s".format(clock()-self.__time0))
        memory = memory_usage()
        if self.__memory == -1 or memory == -1: return
        log("Memory:\t\t "+str(memory)+"MB (+"+str(memory-self.__memory)+"MB)")
        self.__memory = memory


    def __mem_check_limit(self,length):
        self.__mem_before = memory_usage("VmSize")
        log("Expected Memory: {}MB".format(self.__mem_before + (self.__mem_max*length)))
        if self.__mem_limit < (self.__mem_before + (self.__mem_max*length)):
            return True
        return False


    def __mem_set_max(self,length):
        self.__mem_max = max(self.__mem_max,(memory_usage("VmSize")-self.__mem_before)/float(length))


    def solve(self,length):

        log("Grounded Until:\t {}".format(self.__length))

        # ground if necessary
        grounded = 0
        if self.__length < length:
            if self.__mem and self.__mem_check_limit(length-self.__length):
                log("Skipping: not enough memory for grounding...\n")
                return None
            parts  = [(STEP, [t]) for t in range(self.__length+1,length+1)]
            # parts = parts + [(CHECK,[length])]
            parts += [(CHECK,[t]) for t in range(self.__length+1,length+1)]
            if not self.__move_query: self.__ctl.release_external(clingo.Function(QUERY,[self.__length]))
            log("Grounding...\t "+str(parts))
            if self.__verbose: self.__verbose_start()
            self.__ctl.ground(parts)
            if self.__verbose: self.__verbose_end("Grounding")
            if not self.__move_query: self.__ctl.assign_external(clingo.Function(QUERY,[length]),True)
            self.__ctl.cleanup()
            grounded      = length - self.__length
            self.__length = length

        # blocking or unblocking actions
        if length < self.__last_length:
            log("Blocking actions...")
            for t in range(length+1,self.__last_length+1):
                self.__ctl.assign_external(clingo.Function(SKIP,[t]),True)
        elif self.__last_length < length:
            log("Unblocking actions...")
            for t in range(self.__last_length+1,length+1):
                self.__ctl.assign_external(clingo.Function(SKIP,[t]),False)

        # solve
        log("Solving...",PRINT)
        if self.__verbose: self.__verbose_start()
        if self.__move_query: 
            self.__ctl.assign_external(clingo.Function(QUERY,[self.__last_length]),False)
            self.__ctl.assign_external(clingo.Function(QUERY,[length]),True)
        self.__result = self.__ctl.solve(on_model=self.__on_model)
        if self.__verbose: self.__verbose_end("Solving")
        log(str(self.__result)+"\n")
        if self.__mem and grounded: 
            self.__mem_set_max(grounded)
        self.__last_length = length

        # return
        return self.__result


#
# PLANNER
#


class Planner:

    def run(self,options,clingo_options):

        ctl = clingo.Control(clingo_options)

        # input files
        for i in options['files']:
            ctl.load(i)
        if options['read_stdin']:
            ctl.add(BASE,[],sys.stdin.read())

        # additional programs
        ctl.add(BASE,[],EXTERNALS_PROGRAM)
        if options['forbid_actions']: ctl.add(BASE,[],FORBID_ACTIONS_PROGRAM)
        if options['force_actions']:  ctl.add(BASE,[],FORCE_ACTIONS_PROGRAM)

        # ground base, and set initial query
        ctl.ground([(BASE,[]),(CHECK,[0])])
        ctl.assign_external(clingo.Function(QUERY,[0]),True)

        # solver
        solver = Solver(ctl,options)

        # scheduler
        if sum([1 for i in ['A','B','C'] if options[i] is not None])>1: # check argument error
            raise Exception("Please, choose only one Scheduler: A, B, or C")
        if options['A'] is not None:  # (start,inc,limit,restarts,size,propagate_unsat)
            scheduler = A_Scheduler(options['start'],options['inc'],options['limit'],options['A'],options['propagate_unsat'])
        elif options['B'] is not None:
            scheduler = B_Scheduler(options['start'],options['inc'],options['limit'],options['processes'],options['propagate_unsat'],options['B'])
        elif options['C'] is not None:
            scheduler = C_Scheduler(options['start'],options['C'],  options['limit'],options['propagate_unsat'])
        else: # default
            scheduler = B_Scheduler(options['start'],options['inc'],options['limit'],options['processes'],options['propagate_unsat'],0.9)

        # if verbose, log initial memory usage
        verbose = options['verbose']
        memory = memory_usage()
        if verbose and memory!=-1:
            log("\nMemory: {}MB\n".format(memory))

        # loop
        i=1
        result = None
        max_length = 0
        sol_length = 0
        while True:
            log("Iteration "+str(i))
            if verbose: time0 = clock()
            i += 1
            length = scheduler.next(result)
            if length == None:
                log("PLAN NOT FOUND",PRINT)
                break
            result = solver.solve(length)
            if result is not None and length > max_length: max_length = length
            if result is not None and result.satisfiable:
                log("SATISFIABLE",PRINT)
                sol_length = length
                break
            if verbose: log("Iteration Time:\t {:.2f}s\n".format(clock()-time0))
            #log("\n" + clingo_stats.Stats().summary(ctl),PRINT)
            #if options['stats']:
            #    log(clingo_stats.Stats().statistics(ctl),PRINT)

        # stats
        log("\n" + clingo_stats.Stats().summary(ctl),PRINT)
        if options['stats']:
            log(clingo_stats.Stats().statistics(ctl),PRINT)
            # peak memory
            peak = memory_usage("VmPeak")
            if peak != -1: log("Memory Peak  : {}MB".format(peak),PRINT)
            log("Max. Length  : {} steps".format(max_length),PRINT)
            if sol_length: log("Sol. Length  : {} steps\n".format(sol_length),PRINT)
            else: log("",PRINT)



#
# ARGUMENT PARSER
#

VERSION = "0.0.1"

class PlannerArgumentParser:

    clingo_help = """
Clingo Options:
  --<option>[=<value>]\t: Set clingo <option> [to <value>]

    """

    usage = "planner.py [options] [files]"

    epilog = """
Default command-line:
planner.py -B 0.9 -M 20 -S 5 -F 0 -T 3000 -i 60 -r 100

planner is part of plasp in Potassco: https://potassco.org/
Get help/report bugs via : https://potassco.org/support
    """

    def run(self):

        # version
        _version = "planner.py version " + VERSION

        # command parser
        _epilog = self.clingo_help + "\nusage: " + self.usage + self.epilog
        cmd_parser = argparse.ArgumentParser(description="An ASP Planner",
            usage=self.usage,epilog=_epilog,formatter_class=argparse.RawDescriptionHelpFormatter,
            add_help=False)

        # basic
        basic = cmd_parser.add_argument_group('Basic Options')
        basic.add_argument('-h','--help',action='help',help='Print help and exit')
        basic.add_argument('-',dest='read_stdin',action='store_true',help=argparse.SUPPRESS)
        basic.add_argument('-c','--const',dest='constants',action="append",help=argparse.SUPPRESS,default=[])
        basic.add_argument('-v','--verbose',dest='verbose',action="store_true",help="Be a bit more verbose")
        basic.add_argument('--stats',dest='stats',action="store_true",help="Print statistics")
        basic.add_argument('--outf',dest='outf',type=int,metavar="n",help="Use {0=default|1=competition} output",default=0,choices=[0,1])
      

        # Solving Options
        solving = cmd_parser.add_argument_group('Solving Options')
        solving.add_argument('--query-at-last',dest='move_query',action="store_false",help="Fix query always at the last (grounded) time point")
        solving.add_argument('--forbid-actions',dest='forbid_actions',action="store_true",help="Forbid actions at time points after current plan length")
        solving.add_argument('--force-actions',dest='force_actions',action="store_true",help="Force at least one action at time points before current plan length")


        # Scheduler
        scheduler = cmd_parser.add_argument_group('Scheduler Options')

        # A, B or C
        scheduler.add_argument('-A',dest='A',help="Run algorithm A with parameter n (range 1 to 50)",
                                metavar='n',default=None,type=int)
        scheduler.add_argument('-B',dest='B',help="Run algorithm B with parameter r (range 0.1 to 0.9999) (default 0.9)",
                                metavar='r',default=None,type=float)
        scheduler.add_argument('-C',dest='C',help="Run algorithm C with parameter r (range 0.2 to 2.0)",
                                metavar='r',default=None,type=float)
        # Options
        scheduler.add_argument('-M',dest='processes',help="With algorithm B, use maximum n processes (default -M 20)",
                                metavar='n',default=20,type=int)
        scheduler.add_argument('-S',dest='inc',help="Step for horizon lengths 0, n, 2n, 3n, ... (default -S 5, algorithms A and B only)",
                                metavar='n',default=5,type=int)
        scheduler.add_argument('-F',dest='start',help="Starting horizon length (default -F 0)",
                                metavar='n',default=0,type=int)
        scheduler.add_argument('-T',dest='limit',help="Ending horizon length (default -T 3000)",
                                metavar='n',default=3000,type=int)
        scheduler.add_argument('-i',dest='conflicts_per_restart',help="Restart interval is n (default -i 60, use 0 for leaving open the restart policy)",
                                metavar='n',default=60,type=int)
        scheduler.add_argument('-m',dest='check_mem',help="Allocating max. n MB of memory (0 for not checking, default -m 0, only for UNIX)", # 8192
                                metavar='n',default=0,type=int)

        # New Options
        scheduler.add_argument('-r',dest='restarts_per_solve',help="Number of restarts per solve call (default -r 100)",
                                metavar='n',default=100,type=int)
        scheduler.add_argument('--keep-after-unsat',dest='propagate_unsat',help="After finding n to be UNSAT, do keep runs with m<n",
                                action="store_false")

        # parse
        options, unknown = cmd_parser.parse_known_args()
        options = vars(options)

        # separate files, and clingo options
        options['files'], clingo_options = [], []
        for i in unknown:
            if (re.match(r'^-',i)): clingo_options.append(i)
            else:                   options['files'].append(i)
        if options['files'] == []: options['read_stdin'] = True

        # always append statistics for using Stats()
        clingo_options.append("--stats")

        # add constants to clingo_options
        for i in options['constants']:
            clingo_options.append("-c {}".format(i))

        # set log options
        global log_level
        global outf
        log_level = PRINT if not options['verbose'] else VERBOSE
        outf      = options['outf']

        # log version
        log(_version,PRINT)

        # return
        return options, clingo_options



#
# MAIN
#

if __name__ == "__main__":
    options, clingo_options = PlannerArgumentParser().run()
    Planner().run(options,clingo_options)



