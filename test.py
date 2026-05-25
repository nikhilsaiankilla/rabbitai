import traceback
from agent import run

try:
    result = run(
        repo_name="nikhilsaiankilla/portfolio", # Replace with your repository name
        pr_number=11, # Replace with the pull request number you want to analyze
    )
    print(result)
except Exception as e:
    traceback.print_exc()
