from setuptools import setup, find_packages

setup(
    name="orion-inference",
    version="1.0.0",
    description=(
        "Hierarchical Memory Orchestration for AI Inference — "
        "regime-based framework from Nature Computational Science"
    ),
    packages=find_packages(exclude=["tests*", "experiments*"]),
    python_requires=">=3.9",
    install_requires=[
        "numpy>=1.24",
        "scipy>=1.11",
    ],
    extras_require={
        "plot": ["matplotlib>=3.8"],
        "gpu":  ["torch>=2.4", "pynvml>=11.0"],
        "dev":  ["pytest>=7.4"],
    },
    entry_points={
        "console_scripts": [
            "orion-sweep=experiments.run_regime_sweep:main",
            "orion-table2=experiments.reproduce_table2:main",
            "orion-table3=experiments.reproduce_table3:main",
            "orion-figure2=experiments.reproduce_figure2:main",
            "orion-ablation=experiments.reproduce_classifier_ablation:main",
        ],
    },
)
