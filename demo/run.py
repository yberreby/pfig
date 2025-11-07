import sys

from pfig import run

from .figures import FIGURES

if __name__ == "__main__":
    run(FIGURES, root="exported", style="default", argv=sys.argv[1:])
