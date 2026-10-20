# InsightFace installation during image builds

The `PyDataType_TYPEOBJ`, `PyDataType_KIND`, and
`_PyUFuncObject_GET_ITEM_DATA` compiler errors occur while building
InsightFace's Cython extension. The app's `numpy<2` runtime dependency does
not constrain NumPy or Cython in uv's isolated build environment.

Use the root `build-constraints.txt` for **build dependencies**. Keep build
isolation enabled. Installing NumPy in the bench first does not constrain an
isolated build, and Frappe's site install hooks run too late to fix this error.

## Docker / Frappe Cloud image build

In the failing Dockerfile RUN instruction, preserve both existing cache and
app bind mounts. Replace the command after the mounts with:

```dockerfile
UV_BUILD_CONSTRAINT=/home/frappe/context/apps/karmavitta/build-constraints.txt \
    bench get-app file:///home/frappe/context/apps/karmavitta
```

The constraints file must be present in the app source used by the image
builder. The existing bind mount makes it available at the path above for
that RUN instruction. The environment variable is inherited by Bench's
`uv pip install` subprocess.

On managed Frappe Cloud, the Dockerfile is generated outside this repository.
Ask the bench/image build administrator or Frappe Cloud support to apply
this build environment setting to the failing app installation step. A site
configuration value or an environment variable added only to running workers
will not affect the image build. Rebuild the image after applying the setting.

## Existing self-hosted bench

From the bench directory, if the app has already been cloned:

```bash
UV_BUILD_CONSTRAINT="$PWD/apps/karmavitta/build-constraints.txt" \
    uv pip install --python "$PWD/env/bin/python" -e "$PWD/apps/karmavitta"
```

## Verification

First confirm the image passes the previously failing `bench get-app` step.
Then, in the built bench environment, check the native modules:

```bash
env/bin/python -c 'import numpy, insightface; from insightface.thirdparty.face3d.mesh.cython import mesh_core_cython; print(numpy.__version__, insightface.__version__)'
```

Finally use **Check ArcFace** in Face Attendance Settings to verify model
loading and inference readiness. A successful package build alone does not
verify model downloads or face recognition.

Reference: [uv build constraints](https://docs.astral.sh/uv/pip/compile/#adding-build-constraints).
