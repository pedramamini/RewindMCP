"""
setup script for the rewinddb package.
"""

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="rewinddb",
    version="0.1.0",
    author="Pedram",
    author_email="pedram@example.com",
    description="a python library for interfacing with the rewind.ai sqlite database",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/pedram/rewinddb",
    packages=setuptools.find_packages(),
    classifiers=[
        "programming language :: python :: 3",
        "license :: osi approved :: mit license",
        "operating system :: macos",
    ],
    python_requires=">=3.6",
    install_requires=[
        "pysqlcipher3",
        "fastapi",
        "uvicorn",
        "pydantic",
        "requests",
        "python-dotenv",
        "mcp>=0.1.0",
    ],
)