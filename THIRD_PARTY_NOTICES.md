# Third-party notices

## DigiRG Cloud layout geometry / FFmpeg graphs

Source: https://github.com/DIGIRGCLOUD/DIGIRGCLIPPINGFREE

Revision: `0987925fa4e99c5d90c68239dc8071421c56d121`, `layouts.py` and the camera source-placement preset values in `app.js`.
Adapted in `clipos/video/layouts.py`; integration and normalized crop adapter are CLIPOS changes. The dual-region canvas
and source/composition preview are independently implemented in native Qt,
inspired by the reference player interaction.

```text
MIT License

Copyright (c) 2026 DigiRG Cloud (@ft_raj_check) and contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Optional continuous tracking runtime

CLIPOS uses supervision 0.27.0 ByteTrack as a dependency, not a renamed
nearest-neighbor tracker. Source: https://github.com/roboflow/supervision/tree/0.27.0

```text
MIT License

Copyright (c) 2022 Roboflow

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

YOLOX model format/reference: https://github.com/Megvii-BaseDetection/YOLOX
(Apache-2.0). The CLIPOS decoder/preprocessor is independently implemented from
the documented raw-head format. No YOLOX source files or trained model binaries
are vendored by this increment. Users must install trusted, appropriately
licensed model weights explicitly. ONNX Runtime remains an existing dependency.

## Optional neural diarization runtime

sherpa-onnx / sherpa-onnx-core 1.12.34, Apache-2.0:
https://github.com/k2-fsa/sherpa-onnx

CLIPOS invokes the installed runtime's segmentation, speaker embedding and
clustering APIs; it does not rename the existing energy/face heuristic as neural
diarization. The distributed runtime's Apache license is retained at
`resources/licenses/sherpa-onnx-APACHE-2.0.txt`. No trained segmentation/embedding
weights are included or implicitly downloaded. Model licenses, access conditions
and authorized voice processing remain separate requirements for setup. No
third-party account or access-token collection is added to editing.
