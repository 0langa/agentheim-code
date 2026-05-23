from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py


class build_py(_build_py):
    """Ensure removed Python/package-data files do not survive in build_lib."""

    def run(self) -> None:
        build_lib = Path(self.build_lib)
        if build_lib.exists():
            shutil.rmtree(build_lib)
        super().run()


setup(cmdclass={"build_py": build_py})
