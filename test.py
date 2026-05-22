from agent import run

result = run(
    repo_name="nikhilsaiankilla/rabbitai",  # your repo
    pr_number=1,                             # any open PR number
    config_path="config.yaml"
)

print(result)
