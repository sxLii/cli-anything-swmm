from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-swmm",
    version="1.1.0",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    install_requires=[
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
        "pyswmm>=2.0.0",
        "swmm-toolkit>=0.15.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-swmm=cli_anything.swmm.swmm_cli:main",
        ],
    },
    package_data={
        "cli_anything.swmm": ["skills/*.md"],
    },
    python_requires=">=3.10",
)
