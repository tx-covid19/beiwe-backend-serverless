import sys
from os.path import abspath
current_folder = abspath(__file__).rsplit('/', 1)[0]
sys.path.insert(0, current_folder)
sys.stdout = sys.stderr
from downtime import app as application
