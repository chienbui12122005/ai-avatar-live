# AI Teacher Avatar Web

Web app tạo video avatar giáo viên biết nói nhép môi (lip-sync). Người dùng upload ảnh/video của giáo viên cùng một file âm thanh, hệ thống dùng [MuseTalk](https://github.com/TMElyralab/MuseTalk) để sinh video avatar khớp khẩu hình với âm thanh.

## Tính năng

- Form web upload ảnh/video + audio (tùy chọn, có audio mặc định nếu bỏ trống)
- Sinh video lip-sync qua MuseTalk (hỗ trợ **v1.5** và **v1.0**)
- Tinh chỉnh `bbox_shift` cho vùng miệng
- Xem và tải lại danh sách video đã tạo

## Kiến trúc

```
app/
├── main.py              # FastAPI app: các route, upload, sinh config.yaml
└── services/
    └── musetalk.py      # Service layer gọi MuseTalk (tách riêng để dễ đổi engine)
```

App **không bao gồm** MuseTalk — bạn cần cài MuseTalk riêng (kèm models và weights) rồi trỏ `MUSETALK_DIR` tới thư mục đó. Vì cần GPU, app thường chạy trên container/cloud GPU (RunPod, v.v.).

## Yêu cầu

- Python 3.9+
- [MuseTalk](https://github.com/TMElyralab/MuseTalk) đã cài đặt với models đã tải sẵn
- `ffmpeg` (mặc định tìm tại `/usr/bin`)
- GPU (khuyến nghị) cho inference

## Cài đặt

```bash
pip install -r requirements.txt
```

## Cấu hình

App đọc cấu hình từ biến môi trường (hỗ trợ file `.env`):

| Biến            | Mặc định                            | Mô tả                                  |
| --------------- | ----------------------------------- | -------------------------------------- |
| `MUSETALK_DIR`  | `/workspace/MuseTalk`               | Thư mục cài đặt MuseTalk               |
| `UPLOAD_DIR`    | `/workspace/avatars`                | Nơi lưu file upload theo từng job      |
| `RESULT_DIR`    | `/workspace/outputs`                | Nơi lưu video kết quả                  |
| `DEFAULT_AUDIO` | `{MUSETALK_DIR}/data/audio/eng.wav` | Audio dùng khi không upload audio      |
| `APP_PORT`      | `8888`                              | Cổng chạy server                       |

Ví dụ `.env`:

```env
MUSETALK_DIR=/workspace/MuseTalk
UPLOAD_DIR=/workspace/avatars
RESULT_DIR=/workspace/outputs
APP_PORT=8888
```

## Chạy

```bash
python -m app.main
```

Hoặc qua uvicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8888
```

Mở `http://localhost:8888`.

## API

| Method | Route               | Mô tả                                             |
| ------ | ------------------- | ------------------------------------------------- |
| GET    | `/`                 | Form upload để sinh video                         |
| POST   | `/generate`         | Nhận file upload, chạy MuseTalk, redirect kết quả |
| GET    | `/result/{job_id}`  | Trang xem video của một job                        |
| GET    | `/video/{job_id}`   | Trả file MP4 kết quả                               |
| GET    | `/videos`           | Danh sách tất cả video đã tạo                      |
| GET    | `/health`           | Trạng thái và cấu hình hiện tại                    |

### `POST /generate` — tham số (multipart form)

| Field          | Kiểu | Bắt buộc | Mặc định | Mô tả                                         |
| -------------- | ---- | -------- | -------- | --------------------------------------------- |
| `teacher_file` | file | có       | —        | Ảnh hoặc video của giáo viên                  |
| `audio_file`   | file | không    | —        | Audio (wav/mp3); trống → dùng `DEFAULT_AUDIO` |
| `bbox_shift`   | int  | không    | `0`      | Dịch bounding box vùng miệng                  |
| `version`      | str  | không    | `v15`    | Phiên bản MuseTalk: `v15` hoặc `v1`           |

## Luồng xử lý

1. Mỗi request `/generate` được gán `job_id` ngẫu nhiên (8 ký tự).
2. File upload được lưu vào `UPLOAD_DIR/{job_id}/`.
3. App sinh `config.yaml` cho MuseTalk với đường dẫn video, audio và `bbox_shift`.
4. `app/services/musetalk.py` gọi `python -m scripts.inference` trong `MUSETALK_DIR`.
5. Video kết quả nằm trong `RESULT_DIR/{job_id}/` và xem được qua `/result/{job_id}`.

## Hạn chế đã biết

- **Xử lý đồng bộ:** `/generate` chạy MuseTalk chặn (blocking) cho tới khi xong — video dài có thể gây timeout. Nên chuyển sang background task/queue.
- **Chưa có xác thực và validate file upload** — cân nhắc trước khi public.
