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
| `MUSETALK_WORKER_URL` | _(trống)_                     | URL worker giữ model nóng; có → render realtime đi qua worker |
| `MUSETALK_CHUNK_SECONDS` | `0`                        | >0 → bật streaming: chia audio thành đoạn ~N giây, phát đoạn đầu sớm |
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
| POST   | `/profiles/{slug}/prepare`     | Build & cache avatar cho một behavior (render nhanh hơn)    |
| POST   | `/profiles/{slug}/delete`      | Xóa profile                                                 |
| POST   | `/api/generate`                | API JSON: audio + profile + intent/behavior → job (cho app ngoài) |
| GET    | `/api/latest`                  | Job render xong mới nhất (cho trang `/live` poll)           |
| GET    | `/live`                        | Sân khấu avatar: idle loop → video AI → idle (cho OBS)      |
| GET    | `/profile-clip/{slug}/{behavior}` | Trả clip của profile (dùng cho trang live)              |
| GET    | `/health`                      | Trạng thái và cấu hình hiện tại                             |

## Đưa avatar lên Zoom/Meet (OBS)

Trang `/live?profile=<slug>` là một "sân khấu" toàn màn hình: phát clip `idle` lặp vô hạn,
tự chuyển sang video AI vừa render xong (kèm tiếng) rồi quay lại idle.

1. Tạo profile có clip `idle` (và `explain`/`question`/`smile`) ở `/profiles`.
2. Mở OBS → **Sources → Browser** → URL `http://<host>:8888/live?profile=<slug>`, đặt kích thước khung hình. Bấm **Interact** một lần và nhấn “Start avatar stage” (để trình duyệt cho phép phát tiếng).
3. OBS → **Start Virtual Camera**.
4. Trong Zoom/Meet chọn camera = **OBS Virtual Camera**.

Khi app AI (hoặc `POST /api/generate`) tạo video mới, `/live` tự phát nó rồi trở về idle —
đúng vòng *idle → speaking → idle*.

## Giảm độ trễ — cache avatar (Phase 5)

MuseTalk có 2 đường render:

- **Batch** (`scripts.inference`, mặc định): mỗi lần render đều load model + tiền xử lý
  (face detection, trích latents) lại từ đầu → chậm.
- **Realtime/cached** (`scripts.realtime_inference`): tiền xử lý avatar **một lần** rồi lưu
  cache ra đĩa; các lần render sau chỉ chạy bước audio→khung hình, **bỏ qua** phần tiền xử lý
  tốn kém, và dùng `--skip_save_images` để không ghi PNG từng khung.

Cách dùng:

1. Vào `/profiles`, sau khi upload clip cho một behavior, bấm **Prepare ⚡**.
   App chạy `scripts.realtime_inference` với `preparation: True` để build cache
   (`{MUSETALK_DIR}/results/v15/avatars/{avatar_id}/`). Behavior đã prepare hiện ký hiệu ⚡.
2. Từ đó, mọi render cho profile+behavior **đã prepare** (qua form `/generate` hoặc
   `POST /api/generate`) tự động đi đường realtime → nhanh hơn. Behavior chưa prepare vẫn
   chạy đường batch như cũ (fallback an toàn).
3. Upload lại clip cho một behavior sẽ **xóa** trạng thái prepared (cache cũ không còn khớp) —
   cần Prepare lại.

### Worker giữ model nóng (độ trễ thấp nhất)

`scripts.realtime_inference` tải lại VAE + UNet + Whisper **mỗi lần chạy** (vài chục giây
cold start). Worker `worker/musetalk_worker.py` load model **một lần** rồi phục vụ render
qua HTTP, giữ luôn vật liệu avatar trong RAM → mỗi lần render chỉ còn phần audio→khung hình.

Chạy **2 process** trên cùng pod:

```bash
# Terminal 1 — worker giữ model nóng
./run_worker.sh                       # mặc định cổng 8899

# Terminal 2 — web app, trỏ tới worker
export MUSETALK_WORKER_URL=http://127.0.0.1:8899
./run.sh
```

Khi `MUSETALK_WORKER_URL` được set, mọi render của profile+behavior **đã prepare** tự đi
qua worker (load code path: worker → subprocess realtime → batch, fallback an toàn nếu
worker chưa bật). Kiểm tra worker sống qua `/health` (mục `worker`).

Render đi qua worker = dùng đúng vòng inference của `realtime_inference` (audio feature →
UNet → VAE decode → blend → ffmpeg mux) nhưng model + vật liệu avatar không nạp lại.
Worker chỉ **render** (1 lần/GPU, có khóa); **prepare** vẫn do `scripts.realtime_inference`
chạy nền (một lần, không cần nóng).

> Worker tự `chdir` vào `MUSETALK_DIR` và dùng cache avatar ở `results/v15/avatars/...`,
> nên phải **prepare trước** (nút Prepare ⚡) rồi worker mới render được behavior đó.

### Streaming chunk audio (giảm time-to-first-frame)

Với câu trả lời dài, chờ render xong cả clip mới phát thì trễ. Bật streaming để chia audio
thành đoạn ngắn, render từng đoạn và **phát đoạn đầu ngay** trong khi các đoạn sau còn render:

```bash
export MUSETALK_WORKER_URL=http://127.0.0.1:8899
export MUSETALK_CHUNK_SECONDS=3        # mỗi đoạn ~3s; 0 = tắt streaming
./run.sh
```

Khi bật (và profile+behavior đã prepare), render đi qua worker `POST /render_chunked`:

1. Worker tách audio bằng ffmpeg, render **tuần tự từng đoạn**, ghi `{job}_000.mp4`,
   `{job}_001.mp4`… vào `RESULT_DIR/{job}/` và cập nhật `segments.json` ngay sau mỗi đoạn.
2. Chỉ số tư thế (pose) của avatar **chạy liên tục xuyên các đoạn** nên đầu/người không
   giật về frame 0 ở ranh giới đoạn (chỉ còn vệt nối rất nhỏ do nạp file).
3. Trang `/live` poll `/job/{id}/segments`, phát đoạn 0 ngay khi có, nối tiếp các đoạn kế
   (badge hiện *speaking (stream)*), hết thì về idle. Cuối cùng worker ghép full `{job}.mp4`
   để `/video` và `/videos` vẫn dùng được (các file `_NNN.mp4` bị ẩn khỏi danh sách).

`/api/latest` trả cả job chunked **đang chạy** (ngay khi có đoạn đầu) nên stage bắt đầu sớm,
không đợi render xong. Tắt streaming (bỏ `MUSETALK_CHUNK_SECONDS` hoặc =0) thì quay về phát
một video nguyên khối như cũ.

> Tradeoff: tách audio làm mất ngữ cảnh xuyên đoạn nên khẩu hình ở chỗ nối có thể hơi lệch
> nhẹ. Đoạn càng ngắn → bắt đầu càng sớm nhưng càng nhiều mối nối. ~2–4s thường là cân bằng tốt.

> **Cần verify trên pod:** bản MuseTalk của bạn phải có `scripts.realtime_inference` hỗ trợ
> `--skip_save_images` và cache dưới `results/v15/avatars/...` (đúng theo repo TMElyralab/MuseTalk
> hiện tại). Prepare mặc định dùng **v15**; nếu render v1 thì cần prepare ở v1 (cache lưu khác chỗ).
> Nếu script khác phiên bản, chỉ cần chỉnh `app/services/musetalk_realtime.py`.

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
