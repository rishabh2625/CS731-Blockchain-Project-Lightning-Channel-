"""Public command-line entry point."""
import argparse
from .lab import run_scenarios

def main():
    parser=argparse.ArgumentParser(description='Lightning channel laboratory')
    sub=parser.add_subparsers(dest='command',required=True)
    demo=sub.add_parser('demo',help='Run Bitcoin Core-backed scenarios')
    demo.add_argument('--output',default='evidence/regtest')
    demo.add_argument('--case',action='append',dest='cases')
    demo.add_argument('--chain',choices=['regtest','signet'],default='regtest',help='signet creates a private OP_TRUE test chain')
    bench=sub.add_parser('benchmark',help='Measure local durable payment latency')
    bench.add_argument('--output',default='evidence/benchmark.json')
    bench.add_argument('--payments',type=int,default=50)
    bench.add_argument('--runs',type=int,default=3)
    args=parser.parse_args()
    if args.command=='demo': run_scenarios(args.output,args.cases,args.chain)
    elif args.command=='benchmark':
        from .benchmark import run
        run(args.output,args.payments,args.runs)

if __name__=='__main__': main()
