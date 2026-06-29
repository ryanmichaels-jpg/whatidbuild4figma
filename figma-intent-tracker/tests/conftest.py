import os
import sys

# make the project modules importable when pytest collects from tests/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
