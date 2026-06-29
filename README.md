# AI Teacher Avatar Web

Web app tạo video avatar giáo viên biết nói nhép môi (lip-sync). Người dùng upload ảnh/video của giáo viên cùng một file âm thanh, hệ thống dùng [MuseTalk](https://github.com/TMElyralab/MuseTalk) để sinh video avatar khớp khẩu hình với âm thanh.

## Tính năng

- Form web upload ảnh/video + audio (tùy chọn, có audio mặc định nếu bỏ trống)
- Sinh video lip-sync qua MuseTalk (hỗ trợ **v1.5** và **v1.0**)
- **Render nền (background job):** bấm Generate không chờ trắng trang — chuyển ngay sang trang job
- **Job status + log trực tiếp:** trạng thái `pending → running → done / failed`, xem log render realtime trên web (biết lỗi do ảnh / audio / face detection / model)
- **Avatar profile:** mỗi giáo viên có nhiều clip theo behavior (`idle / explain / question / smile`), upload một lần, chọn behavior khi generate
- Tinh chỉnh `bbox_shift` cho vùng miệng
- Quản lý video đã tạo: xem, tải, **xóa**, kèm size + thời điểm tạo

## Kiến trúc

```
app/
├── main.py              # FastAPI: chỉ định nghĩa route (mỏng)
├── jobs.py              # Job model + registry trong RAM + queue 1 worker chạy render nền
├── profiles.py          # Quản lý teacher profile + behavior clips
├── templates.py         # Render HTML (page wrapper + các trang)
└── services/
    └── musetalk.py      # Gọi MuseTalk, stream output ra log file theo từng dòng
```

Render chạy trong một worker thread **đơn** (serial) nên GPU không bao giờ bị chạy 2 job
cùng lúc. Trạng thái job nằm trong RAM (mất khi restart) nhưng log và video vẫn còn trên đĩa.

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
| `PROFILE_DIR`   | `/workspace/profiles`               | Nơi lưu teacher profile + behavior clip|
| `LOG_DIR`       | `/workspace/logs`                   | Nơi lưu log render theo từng job       |
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

| Method | Route                          | Mô tả                                                       |
| ------ | ------------------------------ | ----------------------------------------------------------- |
| GET    | `/`                            | Form sinh video (chọn profile+behavior hoặc upload clip)    |
| POST   | `/generate`                    | Tạo job, render nền, redirect sang trang job                |
| GET    | `/job/{job_id}`                | Trang job: status + log trực tiếp + video khi xong          |
| GET    | `/job/{job_id}/status`         | JSON status + log (trang job poll mỗi 1.5s)                 |
| GET    | `/result/{job_id}`             | Trang xem video của một job                                 |
| GET    | `/video/{job_id}`              | Trả file MP4 kết quả                                        |
| GET    | `/videos`                      | Danh sách video đã tạo (size, thời điểm)                    |
| POST   | `/videos/{job_id}/delete`      | Xóa video + upload + log của job                            |
| GET    | `/profiles`                    | Danh sách profile + tạo mới + upload clip                   |
| POST   | `/profiles`                    | Tạo profile mới                                             |
| POST   | `/profiles/{slug}/upload`      | Upload clip cho một behavior                                |
| POST   | `/profiles/{slug}/delete`      | Xóa profile                                                 |
| GET    | `/health`                      | Trạng thái và cấu hình hiện tại                             |

### `POST /generate` — tham số (multipart form)

| Field          | Kiểu | Bắt buộc | Mặc định | Mô tả                                         |
| -------------- | ---- | -------- | -------- | --------------------------------------------- |
| `teacher_file` | file | có       | —        | Ảnh hoặc video của giáo viên                  |
| `audio_file`   | file | không    | —        | Audio (wav/mp3); trống → dùng `DEFAULT_AUDIO` |
| `bbox_shift`   | int  | không    | `0`      | Dịch bounding box vùng miệng                  |
| `version`      | str  | không    | `v15`    | Phiên bản MuseTalk: `v15` hoặc `v1`           |

## Luồng xử lý

1. Mỗi request `/generate` được gán `job_id` ngẫu nhiên.
2. Nguồn teacher: nếu upload clip thì dùng clip đó (ưu tiên), nếu không thì lấy clip theo `profile` + `behavior`.
3. File upload được lưu vào `UPLOAD_DIR/{job_id}/`; app sinh `config.yaml` cho MuseTalk.
4. Job được đẩy vào queue 1 worker; app **redirect ngay** sang `/job/{job_id}` (không chờ).
5. Worker gọi `app/services/musetalk.py` → `python -m scripts.inference`, stream output ra `LOG_DIR/{job_id}.log`.
6. Trang job poll `/job/{job_id}/status` mỗi 1.5s, hiển thị log realtime; khi `done` nhúng video.
7. Video kết quả nằm trong `RESULT_DIR/{job_id}/`.

## Avatar profile

- Tạo profile cho từng giáo viên ở `/profiles`, mỗi profile có clip riêng cho từng behavior: `idle / explain / question / smile`.
- Upload clip một lần; khi generate chỉ cần chọn profile + behavior thay vì upload lại.
- Profile lưu tại `PROFILE_DIR/{slug}/` kèm `profile.json`.

## Hạn chế đã biết

- **Trạng thái job trong RAM:** mất khi restart server (log + video vẫn còn trên đĩa). Nếu cần bền qua restart, chuyển sang JSON/SQLite.
- **Chưa có xác thực và validate file upload** — cân nhắc trước khi public.
- **Cache avatar mới ở mức tái dùng clip;** caching latents thật sự (giảm trễ) thuộc hướng realtime (`scripts.realtime_inference`) — Phase 5.
