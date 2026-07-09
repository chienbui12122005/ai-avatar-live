#!/bin/bash
# Script setup SSH key persistent cho RunPod
# Giúp giữ SSH key không bị mất khi restart pod (lưu trong /workspace và khôi phục vào ~/.ssh)

set -e

PERSISTENT_SSH_DIR="/workspace/.ssh"
HOME_SSH_DIR="$HOME/.ssh"

echo "===== Bắt đầu thiết lập SSH Key Persistent trên RunPod ====="

# 1. Tạo thư mục persistent trên /workspace nếu chưa có
mkdir -p "$PERSISTENT_SSH_DIR"

# 2. Tạo hoặc đọc SSH Key
if [ ! -f "$PERSISTENT_SSH_DIR/id_ed25519" ]; then
    echo "Chưa tìm thấy SSH key trong thư mục lưu trữ persistent ($PERSISTENT_SSH_DIR)."
    echo "Đang khởi tạo SSH key mới (loại ed25519)..."
    ssh-keygen -t ed25519 -f "$PERSISTENT_SSH_DIR/id_ed25519" -N "" -C "runpod-ai-avatar"
    echo "Khởi tạo thành công!"
else
    echo "Đã tìm thấy SSH key có sẵn trong thư mục persistent."
fi

# 3. Khôi phục/Sao chép SSH key vào thư mục ~/.ssh của container hiện tại
echo "Đang liên kết SSH key vào thư mục mặc định của hệ thống (~/.ssh)..."
mkdir -p "$HOME_SSH_DIR"
chmod 700 "$HOME_SSH_DIR"

cp "$PERSISTENT_SSH_DIR/id_ed25519" "$HOME_SSH_DIR/id_ed25519"
cp "$PERSISTENT_SSH_DIR/id_ed25519.pub" "$HOME_SSH_DIR/id_ed25519.pub"

chmod 600 "$HOME_SSH_DIR/id_ed25519"
chmod 644 "$HOME_SSH_DIR/id_ed25519.pub"

# 4. Tự động thêm GitHub vào known_hosts để không bị hỏi xác nhận (yes/no) khi push/pull
echo "Đang quét mã xác nhận của GitHub (GitHub SSH fingerprint)..."
ssh-keyscan -t ed25519 github.com >> "$HOME_SSH_DIR/known_hosts" 2>/dev/null || true

# 5. Tự động chạy agent và add key
eval "$(ssh-agent -s)"
ssh-add "$HOME_SSH_DIR/id_ed25519"

echo "=========================================================="
echo "✔ THIẾT LẬP THÀNH CÔNG!"
echo "=========================================================="
echo "Mẹo: Từ giờ, mỗi lần restart pod, bạn chỉ cần chạy lại file này để phục hồi SSH key lập tức:"
echo "  ./setup_ssh.sh"
echo "=========================================================="
echo "ĐÂY LÀ PUBLIC KEY CỦA BẠN (Dùng để import vào GitHub):"
echo "----------------------------------------------------------"
cat "$HOME_SSH_DIR/id_ed25519.pub"
echo "----------------------------------------------------------"
echo "Các bước add key vào GitHub:"
echo "1. Copy dòng public key trên (bắt đầu bằng ssh-ed25519...)."
echo "2. Truy cập: https://github.com/settings/keys"
echo "3. Nhấn 'New SSH key', dán key vừa copy vào ô Key, đặt tiêu đề và lưu lại."
echo "4. Test kết nối bằng lệnh: ssh -T git@github.com"
echo "=========================================================="
