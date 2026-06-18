import os
import sys


PATCHED = False


def install_hooks():
    global PATCHED
    if PATCHED:
        return
    PATCHED = True


if __name__ == "__main__":
    if len(sys.argv) > 1:
        import runpy
        target = sys.argv[1]
        sys.argv = sys.argv[1:]
        runpy.run_path(target, run_name="__main__")
    else:
        print("anzuelo monitor: no target script specified", file=sys.stderr)
        sys.exit(1)
