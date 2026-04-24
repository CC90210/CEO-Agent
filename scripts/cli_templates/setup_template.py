"""
Setup Template for CLI-Anything tools.
Copy this file to your CLI project as setup.py and customize.

Replace all instances of <SOFTWARE> with your tool name (lowercase).
Replace <DESCRIPTION> with a one-line description.
Replace <DEPENDENCIES> with any additional pip packages needed.
"""

from setuptools import find_namespace_packages, setup

# ============================================================
# CUSTOMIZE THESE VALUES
# ============================================================
SOFTWARE_NAME = "<SOFTWARE>"  # e.g., "gimp", "blender", "notion"
VERSION = "1.0.0"
DESCRIPTION = "<DESCRIPTION>"
AUTHOR = "Business-Empire-Agent"
# ============================================================

setup(
    name=f"cli-anything-{SOFTWARE_NAME}",
    version=VERSION,
    description=DESCRIPTION,
    author=AUTHOR,
    packages=find_namespace_packages(include=["cli_anything", "cli_anything.*"]),
    install_requires=[
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
        # <DEPENDENCIES> — add software-specific deps here
    ],
    entry_points={
        "console_scripts": [
            f"cli-anything-{SOFTWARE_NAME}=cli_anything.{SOFTWARE_NAME}.{SOFTWARE_NAME}_cli:main",
        ],
    },
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Libraries",
    ],
)
