"""Print a safe Locust command for a named, bounded profile."""

import argparse
import shlex

from performance.profiles import get_profile


def command(profile_name: str, host: str, prefix: str) -> list[str]:
    profile = get_profile(profile_name)
    return [
        "locust",
        "-f",
        "performance/locustfile.py",
        "--headless",
        "--host",
        host,
        "--users",
        str(profile.users),
        "--spawn-rate",
        str(profile.spawn_rate),
        "--run-time",
        profile.run_time,
        "--csv",
        prefix,
        "--only-summary",
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("smoke", "baseline", "stress"), required=True)
    parser.add_argument("--host", default="http://127.0.0.1:8000")
    parser.add_argument("--csv-prefix", default="../artifacts/performance/runs/latest/locust")
    args = parser.parse_args()
    print(shlex.join(command(args.profile, args.host, args.csv_prefix)))


if __name__ == "__main__":
    main()
