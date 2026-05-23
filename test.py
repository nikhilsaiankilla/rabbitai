import traceback
from agent import run

try:
    result = run(
        repo_name="nikhilsaiankilla/portfolio",
        pr_number=11,
    )
    print(result)
except Exception as e:
    traceback.print_exc()
