# Third-party dependency and license notices

## Scope

This is a release review of direct dependencies declared in `package.json`, `engine/requirements.txt`, `requirements-desktop.txt`, and `src-tauri/Cargo.toml`. It is not a generated bill of materials and does not replace the complete license texts required for redistribution. Transitive packages are resolved in `package-lock.json`, `src-tauri/Cargo.lock`, and installed Python metadata.

No root `LICENSE` or `COPYING` file was found during the 1 September 2026 repository inventory. Distribution must not proceed until the project's own license and complete third-party notices are approved.

## Python runtime

| Dependency | Declared version | License reference |
|---|---:|---|
| FastAPI | 0.115.6 | [MIT — project repository](https://github.com/fastapi/fastapi/blob/master/LICENSE) |
| Uvicorn | 0.32.1 | [BSD-3-Clause — project repository](https://github.com/encode/uvicorn/blob/master/LICENSE.md) |
| Pydantic | 2.10.3 | [MIT — versioned PyPI record](https://pypi.org/project/pydantic/2.10.3/) |
| Construct | 2.10.70 | [MIT — versioned PyPI record](https://pypi.org/project/construct/2.10.70/) |
| cryptography | 44.0.0 | [Apache-2.0 OR BSD-3-Clause — project license](https://github.com/pyca/cryptography/blob/main/LICENSE) |
| keyring | 25.5.0 | [MIT — project license](https://github.com/jaraco/keyring/blob/main/LICENSE) |
| ReportLab | 4.2.5 | [BSD — publisher FAQ](https://docs.reportlab.com/developerfaqs/) |
| pyHanko | 0.25.1 | [MIT, with bundled-component notices — project license](https://github.com/MatthiasValvekens/pyHanko/blob/master/LICENSE) |
| python-multipart | 0.0.20 | [Apache-2.0 — project license](https://github.com/Kludex/python-multipart/blob/master/LICENSE.txt) |
| pytsk3 | lower bound 20240501 on supported platforms | [Apache-2.0 — project repository](https://github.com/py4n6/pytsk/blob/main/LICENSE) |
| pywebview | lower bound 5.3, fallback shell | [BSD-3-Clause — project license](https://github.com/r0x0r/pywebview/blob/master/LICENSE.md) |

## JavaScript interface

The direct interface stack includes React/React DOM/React Router, Radix primitives, TanStack Virtual, Tauri JavaScript APIs/plugins, Lucide, Sonner, cmdk, class utilities, bundled fonts, Vite, TypeScript, Tailwind CSS, PostCSS, and Autoprefixer.

Authoritative family references:

- [React 18.3.1 MIT license](https://unpkg.com/react@18.3.1/LICENSE)
- [Radix Primitives MIT license](https://github.com/radix-ui/primitives/blob/main/LICENSE)
- [TanStack Virtual MIT license](https://github.com/TanStack/virtual/blob/main/LICENSE)
- [Tauri license: Apache-2.0 or MIT](https://github.com/tauri-apps/tauri)
- [Lucide ISC license](https://github.com/lucide-icons/lucide/blob/main/LICENSE)
- [Vite MIT license](https://github.com/vitejs/vite/blob/main/LICENSE)
- [TypeScript Apache-2.0 license](https://github.com/microsoft/TypeScript/blob/main/LICENSE.txt)
- [Tailwind CSS MIT license](https://github.com/tailwindlabs/tailwindcss/blob/main/LICENSE)
- [Inter SIL Open Font License 1.1](https://github.com/rsms/inter/blob/master/LICENSE.txt)
- [JetBrains Mono SIL Open Font License 1.1](https://github.com/JetBrains/JetBrainsMono/blob/master/OFL.txt)

Exact direct versions are recorded in `package.json`; exact resolved versions and integrity values are in `package-lock.json`.

## Rust desktop shell

Direct crates are Tauri and its build/dialog/filesystem/shell/window-state crates, Serde, serde_json, and ureq. Exact resolution is in `src-tauri/Cargo.lock`. Primary references:

- [Tauri repository and dual license](https://github.com/tauri-apps/tauri)
- [Serde MIT or Apache-2.0](https://github.com/serde-rs/serde)
- [ureq MIT or Apache-2.0](https://github.com/algesten/ureq)

## Release actions

1. Generate complete JavaScript, Python, and Rust bills of materials from the locked release environment.
2. Collect the exact license text and copyright notice for every distributed direct and transitive component.
3. Review conditional, bundled, font, native, and optional components, including `uvicorn[standard]`, `pytsk3`, cryptography's native libraries, pyHanko bundled notices, and Tauri/WebView2.
4. Add the approved Pramaan project license.
5. Include notices in installers and source distributions, then archive the reviewed inventory with the release.

Evidence: the four dependency manifests named above, both lockfiles, the linked upstream license sources, and the repository license-file inventory on 1 September 2026.
