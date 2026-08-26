# Publishing OpenTune to PyPI

OpenTune publishes through GitHub Actions with PyPI Trusted Publishing. This avoids storing a PyPI API token in GitHub or in the repository.

## One-time setup

1. Create and verify an account at [PyPI](https://pypi.org/account/register/).
2. In PyPI, open **Your projects → Publishing**. If `opentune` does not exist yet, open **Your account → Publishing** and add a pending publisher instead.
3. Add a **GitHub Actions** trusted publisher with these values:

   | Field | Value |
   | --- | --- |
   | PyPI project name | `opentune` |
   | Owner | Your GitHub user or organization that owns this repository |
   | Repository name | `opentune` |
   | Workflow filename | `publish-pypi.yml` |
   | Environment | `pypi` |

4. In GitHub, open **Settings → Environments → New environment**, create `pypi`, and optionally restrict it to protected tags or require approval before a release publishes.

PyPI does not reserve a pending project name until the first publish. Confirm that `opentune` is available before creating the release, or choose a unique replacement name and update `project.name` in `pyproject.toml` plus this document.

## Publish a release

1. Update the version in both `pyproject.toml` and `opentune/__init__.py`. PyPI does not permit re-uploading an already published version.
2. Run the local checks:

   ```sh
   make test
   python3 -m pip install --upgrade build twine
   make build
   python3 -m twine check dist/*
   ```

3. Commit and push the release changes, including the version bump.
4. Create and publish a GitHub Release with a matching tag, for example `v0.8.5`.
5. The **Publish to PyPI** workflow builds, validates, and uploads the release. Approve the `pypi` environment if GitHub asks.
6. Verify the release, then users can install or update from anywhere:

   ```sh
   pipx install opentune
   pipx upgrade opentune
   ```

## First release note

The first release is the point at which PyPI creates the project and converts the pending publisher into a normal publisher. If the name was claimed before the workflow runs, the workflow will fail safely; choose a different project name and update the metadata before retrying.

## License

OpenTune is distributed under Apache License 2.0. The root `LICENSE` file contains the full license text, and `NOTICE` contains the project attribution notice. PyPI metadata declares the SPDX expression `Apache-2.0` and includes the license file in distribution archives.
