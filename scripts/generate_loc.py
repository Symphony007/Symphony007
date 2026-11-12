
import os
import re
import json
import base64
import subprocess
import tempfile

from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent

REPO_FILE = ROOT / "loc-repos.txt"
LANG_FILE = ROOT / "cloc-lang.txt"
OUTPUT = ROOT / "assets" / "loc-stats.svg"

# Directories that should never contribute to project LOC.
EXCLUDED_DIRS = [
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".output",
    ".cache",
    "cache",
    "coverage",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "site-packages",
    "bower_components",
    "target",
    "out",
    "bin",
    "obj",
    "Pods",
    "DerivedData",
    ".gradle",
    ".idea",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "htmlcov",
    "storybook-static",
    "playwright-report",
    "test-results",
    ".turbo",
]

# Data, documentation and generated-file extensions.
EXCLUDED_EXTENSIONS = [
    "json",
    "json5",
    "jsonl",
    "lock",
    "map",
    "md",
    "mdx",
    "txt",
    "svg",
    "ipynb",
    "csv",
]

COLORS = [
    "#58A6FF",
    "#3FB950",
    "#D2A8FF",
    "#F0883E",
    "#F778BA",
    "#79C0FF",
    "#E3B341",
    "#56D4DD",
    "#A5D6FF",
    "#8B949E",
]


def read_repositories():
    if not REPO_FILE.exists():
        raise FileNotFoundError("loc-repos.txt not found")

    repos = []

    for line in REPO_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if not re.fullmatch(
            r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", line
        ):
            raise ValueError(f"Invalid repository: {line}")

        repos.append(line)

    return list(dict.fromkeys(repos))


def clone_repository(repo, destination):
    token = os.environ.get("LOC_GITHUB_TOKEN")

    url = f"https://github.com/{repo}.git"
    env = os.environ.copy()

    if token:
        credentials = base64.b64encode(
            f"x-access-token:{token}".encode()
        ).decode()

        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.extraheader"
        env["GIT_CONFIG_VALUE_0"] = (
            f"AUTHORIZATION: basic {credentials}"
        )

    subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--depth",
            "1",
            url,
            str(destination),
        ],
        check=True,
        env=env,
    )


def count_repository(repo, destination):
    clone_repository(repo, destination)

    command = [
        "cloc",
        "--json",
        "--quiet",
        "--vcs",
        "git",
        f"--read-lang-def={LANG_FILE}",
        f"--exclude-dir={','.join(EXCLUDED_DIRS)}",
        f"--exclude-ext={','.join(EXCLUDED_EXTENSIONS)}",

        # Exclude minified files, source maps and lockfiles.
        r"--not-match-f=.*(-lock\.yaml|\.lock|\.min\.(js|css)|\.map)$",

        # Ignore generated files recognised by cloc.
        "--no-autogen",

        str(destination),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)

    languages = {}

    for language, stats in data.items():
        if language in ("header", "SUM"):
            continue

        code = int(stats.get("code", 0))
        files = int(stats.get("nFiles", 0))

        if code > 0:
            languages[language] = {
                "code": code,
                "files": files,
            }

    return languages


def generate_svg(languages, total, repo_count, file_count):

    sorted_languages = sorted(
        languages.items(),
        key=lambda item: item[1]["code"],
        reverse=True,
    )

    # Display the top 8 languages.
    visible = sorted_languages[:8]

    if len(sorted_languages) > 8:
        other_code = sum(
            stats["code"]
            for _, stats in sorted_languages[8:]
        )

        visible.append(
            (
                "Other",
                {
                    "code": other_code,
                    "files": 0,
                },
            )
        )

    width = 760
    height = 180 + len(visible) * 57 + 35

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',

        """
        <defs>
          <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#161B22"/>
            <stop offset="100%" stop-color="#0D1117"/>
          </linearGradient>
        </defs>
        """,

        f'<rect width="{width}" height="{height}" '
        f'rx="16" fill="url(#bg)" stroke="#30363D"/>',

        '<g font-family="Segoe UI, Arial, sans-serif">',

        '<text x="32" y="40" font-size="15" '
        'fill="#8B949E" font-weight="600">'
        'CODEBASE STATISTICS</text>',

        f'<text x="32" y="103" font-size="48" '
        f'fill="#F0F6FC" font-weight="700">{total:,}</text>',

        '<text x="34" y="128" font-size="12" '
        'fill="#8B949E">LINES OF CODE</text>',

        f'<text x="550" y="76" font-size="14" '
        f'fill="#C9D1D9">{repo_count} repositories</text>',

        f'<text x="550" y="100" font-size="14" '
        f'fill="#C9D1D9">{file_count:,} source files</text>',

        '<line x1="32" y1="151" x2="728" y2="151" '
        'stroke="#30363D"/>',
    ]

    y = 190

    for index, (language, stats) in enumerate(visible):
        code = stats["code"]

        percentage = (
            code / total * 100
            if total > 0
            else 0
        )

        color = COLORS[index % len(COLORS)]

        bar_width = 696 * percentage / 100

        parts.extend([
            f'<text x="32" y="{y}" font-size="14" '
            f'fill="#E6EDF3">{escape(language)}</text>',

            f'<text x="728" y="{y}" text-anchor="end" '
            f'font-size="13" fill="#8B949E">'
            f'{code:,} LOC · {percentage:.1f}%</text>',

            f'<rect x="32" y="{y + 13}" width="696" '
            f'height="9" rx="5" fill="#30363D"/>',

            f'<rect x="32" y="{y + 13}" '
            f'width="{bar_width:.2f}" '
            f'height="9" rx="5" fill="{color}"/>',
        ])

        y += 57

    parts.extend([
        f'<text x="32" y="{height - 18}" font-size="11" '
        f'fill="#6E7681">Generated automatically · cloc · '
        f'Code lines only · Comments and blanks excluded</text>',

        '</g></svg>',
    ])

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT.write_text(
        "\n".join(parts),
        encoding="utf-8",
    )


def main():

    repos = read_repositories()

    if not repos:
        raise RuntimeError("No repositories configured.")

    if not LANG_FILE.exists():
        raise FileNotFoundError("cloc-lang.txt not found")

    all_languages = {}
    total_files = 0

    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)

        for index, repo in enumerate(repos):

            print(f"\nScanning {repo}...")

            destination = temp_path / f"repo-{index}"

            languages = count_repository(
                repo,
                destination,
            )

            for language, stats in languages.items():

                if language not in all_languages:
                    all_languages[language] = {
                        "code": 0,
                        "files": 0,
                    }

                all_languages[language]["code"] += stats["code"]

                all_languages[language]["files"] += stats["files"]

                total_files += stats["files"]

    total_loc = sum(
        stats["code"]
        for stats in all_languages.values()
    )

    generate_svg(
        all_languages,
        total_loc,
        len(repos),
        total_files,
    )

    print("\n" + "=" * 40)
    print("         LOC REPORT")
    print("=" * 40)

    for language, stats in sorted(
        all_languages.items(),
        key=lambda item: item[1]["code"],
        reverse=True,
    ):
        print(
            f"{language:<22} "
            f"{stats['code']:>10,} LOC"
        )

    print("-" * 40)
    print(f"TOTAL LOC:       {total_loc:,}")
    print(f"TOTAL FILES:     {total_files:,}")
    print(f"REPOSITORIES:    {len(repos)}")
    print("=" * 40)

    print(f"\nSVG generated: {OUTPUT}")


if __name__ == "__main__":
    main()
