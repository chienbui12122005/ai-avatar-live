# Hướng dẫn Kiểm thử Nhanh Chức năng Realtime trên RunPod GPU
*(Quy trình kiểm thử trực quan không cần tự chuẩn bị trước tệp video)*

Tài liệu này hướng dẫn cách kiểm thử nhanh các tính năng Realtime, Hot Worker, Audio Chunking và Live Streaming của dự án **AI Teacher Avatar Web** trên máy ảo GPU **RunPod** sử dụng dữ liệu video mẫu đi kèm của MuseTalk và giao diện Playground mới.

---

## 1. Tự động thiết lập SSH Key Persistent (Giữ kết nối GitHub)

Mặc định trên RunPod, thư mục home (`~`) sẽ bị xóa sạch mỗi khi pod bị tắt hoặc khởi động lại, làm mất toàn bộ cấu hình SSH cũ. Để giữ SSH Key kết nối với GitHub bền vững, bạn cần lưu trữ khóa trong phân vùng bền vững `/workspace/.ssh` và cấu hình hệ thống khôi phục mỗi lần bật máy.

Chúng tôi đã viết sẵn script [setup_ssh.sh](file:///Users/tranthuc/workspace/ai-avatar-live/setup_ssh.sh) để tự động hóa toàn bộ luồng này.

### Các bước thực hiện:
1. Mở Terminal trên RunPod, di chuyển tới thư mục dự án và chạy script:
   ```bash
   ./setup_ssh.sh
   ```
2. **Nếu chạy lần đầu tiên:** Script sẽ sinh khóa SSH mới và in **Public Key** lên màn hình. 
   * Hãy sao chép khóa này và thêm vào tài khoản GitHub của bạn tại: [GitHub SSH Keys Settings](https://github.com/settings/keys).
   * Kiểm tra kết nối bằng lệnh: `ssh -T git@github.com`.
3. **Mỗi khi khởi động lại RunPod:** Bạn chỉ cần gõ lại lệnh dưới đây để khôi phục kết nối git ngay lập tức mà không phải tạo lại khóa mới hay add lại vào GitHub:
   ```bash
   ./setup_ssh.sh
   ```

---

## 2. Cấu hình Môi trường (Environment Setup)

Đảm bảo các biến môi trường sau đã được thiết lập (thông qua file `.env` hoặc câu lệnh `export`):

| Biến môi trường | Giá trị khuyến nghị | Mô tả |
| :--- | :--- | :--- |
| `MUSETALK_DIR` | `/workspace/MuseTalk` | Thư mục cài đặt MuseTalk trên RunPod |
| `MUSETALK_WORKER_URL` | `http://127.0.0.1:8899` | Địa chỉ HTTP của Hot Worker |
| `MUSETALK_CHUNK_SECONDS` | `3` | Độ dài mỗi phân đoạn âm thanh chia nhỏ để stream (bằng 3s) |
| `UPLOAD_DIR` | `/workspace/avatars` | Nơi chứa file upload tạm thời |
| `RESULT_DIR` | `/workspace/outputs` | Nơi xuất video kết quả |
| `PROFILE_DIR` | `/workspace/profiles` | Nơi lưu hồ sơ giáo viên |
| `LOG_DIR` | `/workspace/logs` | Nơi chứa log render của từng job |

---

## 3. Các Bước Khởi động Hệ thống (System Startup)

Bạn cần mở **2 Terminal song song** trên RunPod để khởi chạy các tiến trình:

### Terminal 1: Chạy Hot Worker (Mô hình nạp nóng trên VRAM)
Hot Worker có nhiệm vụ load sẵn các weights của UNet, VAE và Whisper lên GPU một lần duy nhất, giúp các lượt render sau không bị mất thời gian nạp lại mô hình.

```bash
# Chỉ định thư mục MuseTalk gốc
export MUSETALK_DIR=/workspace/MuseTalk

# Khởi chạy worker (mặc định mở cổng 8899)
./run_worker.sh
```
*Đợi log hiển thị dòng `[worker] models loaded; ready.` thì chuyển sang Terminal 2.*

### Terminal 2: Chạy Web App chính (Giao diện và Điều phối)
```bash
# Thiết lập các biến kết nối và bật chế độ streaming chunk
export MUSETALK_DIR=/workspace/MuseTalk
export MUSETALK_WORKER_URL=http://127.0.0.1:8899
export MUSETALK_CHUNK_SECONDS=3

# Khởi chạy server FastAPI (mặc định cổng 8888)
./run.sh
```

---

## 4. Khởi tạo Giáo viên Mẫu & Tiền xử lý (Import & Prepare Samples)

Để kiểm thử nhanh mà không cần tìm nguồn video giáo viên bên ngoài, ứng dụng đã tích hợp tính năng tự động nhập các tệp mẫu từ chính mã nguồn của MuseTalk.

1. **Truy cập trang quản lý Profile:**
   Mở trình duyệt và truy cập `http://<runpod-ip>:8888/profiles`.
2. **Khởi tạo Profile từ video mẫu của MuseTalk:**
   * Tìm phần **Import Samples** ở phía bên phải.
   * Click vào nút **⚡ Import Samples from MuseTalk**.
   * Hệ thống sẽ tự động quét thư mục `data/video/` của MuseTalk, phát hiện các tệp như `yongen.mp4` hay `sun.mp4` để tạo ngay các profile tương ứng tên là **Yongen**, **Sun** với đầy đủ các clip hành vi được điền sẵn.
3. **Tiền xử lý (Prepare ⚡) Avatar:**
   * Trong danh sách các profile giáo viên, tìm profile **Yongen**.
   * Tìm dòng hành vi `explain` (hoặc bất kỳ hành vi nào bạn muốn test).
   * Nhấn nút **Prepare ⚡**.
   * Trình duyệt sẽ chuyển sang trang theo dõi Job. Đợi khoảng vài chục giây để GPU xử lý dò mặt và lưu cache latents. Khi hoàn thành, quay lại trang `/profiles` bạn sẽ thấy xuất hiện ký hiệu tia sét `⚡` bên cạnh hành vi đó.

---

## 5. Kiểm thử Realtime Trực quan tại Playground (Realtime Playground)

Sau khi avatar giáo viên mẫu đã sẵn sàng (có biểu tượng `⚡`), bạn có thể tiến hành test luồng phát sóng nói nhép trực tiếp:

1. **Vào giao diện Playground:**
   Click vào tab **⚡ Playground** trên thanh menu (hoặc truy cập `http://<runpod-ip>:8888/playground`).
2. **Chọn Cấu hình:**
   * **Teacher Profile:** Chọn `Yongen` (hoặc profile mẫu bạn vừa prepared).
   * **Behavior:** Chọn `explain` (hành vi đã prepare có biểu tượng tia sét).
   * *Quan sát:* Trình phát video bên phải sẽ tự động nạp và chạy lặp đi lặp lại clip `idle` tắt tiếng để chuẩn bị.
3. **Upload file âm thanh:**
   * Kéo và thả hoặc nhấp vào ô **📁 Click or drag audio file here** để tải lên file ghi âm tiếng nói của bạn (WAV, MP3...).
4. **Bắt đầu Render & Streaming:**
   * Nhấn nút **🚀 Generate & Stream Realtime**.
   * *Hiện tượng xảy ra:*
     * Giao diện log ở góc dưới hiển thị trực tiếp tiến trình render của worker GPU.
     * Thanh tiến trình các bước `1. Upload -> 2. Worker -> 3. Stream -> 4. Done` sẽ sáng đèn theo từng pha.
     * Ngay sau khi worker GPU render xong phân đoạn đầu tiên (~3s đầu), trình phát video bên phải sẽ **tự động bật tiếng** và bắt đầu nói nhép khớp khẩu hình. 
     * Video sẽ phát liên tục các phân đoạn tiếp theo trong khi GPU vẫn đang render các đoạn cuối của file âm thanh.
     * Khi nói xong toàn bộ, video sẽ tự động chuyển mượt mà về trạng thái chờ `idle` ban đầu.

---

## 6. Một số sự cố thường gặp (Troubleshooting)

*   **Lỗi `Không tìm thấy file video mẫu...` khi nhấn Import:**
    *   *Nguyên nhân:* Tham số `MUSETALK_DIR` đang bị sai dẫn đến Web App không tìm thấy thư mục cài đặt của MuseTalk.
    *   *Khắc phục:* Kiểm tra lại biến `MUSETALK_DIR` trong file `.env` hoặc chạy lệnh `ls /workspace/MuseTalk` trên RunPod để xác nhận thư mục chính xác.
*   **Lỗi `ffmpeg not found` hoặc render thất bại không ra video:**
    *   *Nguyên nhân:* Môi trường RunPod thiếu FFmpeg hoặc FFmpeg không nằm trong đường dẫn `/usr/bin`.
    *   *Khắc phục:* Kiểm tra lại xem container đã cài đặt ffmpeg chưa qua lệnh `ffmpeg -version`.
*   **Hành vi không hiện tia sét ⚡:**
    *   *Khắc phục:* Bạn phải nhấn nút **Prepare ⚡** cho từng hành vi của profile đó trên trang `/profiles` trước thì hệ thống mới kích hoạt luồng render realtime. Nếu chưa prepare, nút chạy ở Playground sẽ tự động fallback về chế độ Batch (tải lại model) nên sẽ mất 30s-40s chuẩn bị trước khi phát video.
