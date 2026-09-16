"""PyInstaller hook for AstroPilot's supported Astropy runtime surface."""

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
    is_module_satisfies,
)


def _is_required_astropy_module(name: str) -> bool:
    # WCSAxes is an optional Matplotlib integration. Astropy imports it through
    # pytest.importorskip(), whose Skip exception escapes PyInstaller's isolated
    # submodule collector when Matplotlib is intentionally absent.
    return not (
        name == "astropy.visualization.wcsaxes"
        or name.startswith("astropy.visualization.wcsaxes.")
    )


datas = collect_data_files("astropy")
hiddenimports = collect_submodules(
    "astropy",
    filter=_is_required_astropy_module,
)

for path, target in collect_data_files("astropy", include_py_files=True):
    if path.endswith(("_parsetab.py", "_lextab.py")):
        datas.append((path, target))

if is_module_satisfies("astropy >= 5.0"):
    datas += copy_metadata("astropy")
    datas += copy_metadata("numpy")

hiddenimports += ["numpy.lib.recfunctions"]
