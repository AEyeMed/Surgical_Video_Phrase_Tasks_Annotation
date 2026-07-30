from pathlib import Path

from setuptools import find_packages, setup


ROOT_DIRECTORY = Path(__file__).resolve().parent
DESIGN_DOCUMENTS = [
    str(ROOT_DIRECTORY / name)
    for name in ("DESIGN.md", "DESIGN.clinical-dark.md", "DESIGN.theatre-dim.md")
]
SAMPLE_FILES = [str(path) for path in (ROOT_DIRECTORY / "samples").glob("*.txt")]

setup(
    name="surgui",
    version="1.2.0",
    description="Local-first surgical video annotation workbench",
    url="https://github.com/bnamazi/SurgUI",
    author="Babak Namazi",
    author_email="bnamazi098@gmail.com",
    license="MIT",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Medical Science Apps.",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "PyQt5>=5.15",
        "python-vlc>=3.0",
        "opencv-python>=4.8",
    ],
    extras_require={"labelme": ["labelme>=5.0"]},
    entry_points={"console_scripts": ["surgui = surgui.__main__:main"]},
    data_files=[
        ("surgui_assets", DESIGN_DOCUMENTS),
        ("surgui_assets/samples", SAMPLE_FILES),
    ],
)
