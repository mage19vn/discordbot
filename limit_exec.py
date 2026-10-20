"""Apply Linux resource limits in a child before executing a compiler/program."""

import os
import resource
import sys


def main():
    cpu, memory, file_size = map(int, sys.argv[1:4])
    command = sys.argv[4:]
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_size, file_size))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    os.execvpe(command[0], command, os.environ)


if __name__ == "__main__":
    main()
