# MediaPipe face detector files

- `blaze_face_short_range.tflite`: Google's BlazeFace short-range face detector model (Apache License 2.0),
  downloaded from `https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/`.
  SHA-256 `b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f`.
- `wasm/`: copied from the `@mediapipe/tasks-vision` npm package (Apache License 2.0) by
  `scripts/copy-mediapipe.mjs` when you run `npm install`, `npm run dev` or `npm run build`. Not committed.

The model only finds faces and counts them. It does not recognise who a person is.
Everything runs in the student's browser; no camera image is sent anywhere.
