# Kindle GKPv Static Site

Static site tối giản để đọc Các Giờ Kinh Phụng Vụ trên Kindle Paperwhite browser cũ.

Nguồn nội dung: <https://ktcgkpv.org/readings/prayer>

## Chạy local

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/fetch.py
python -m http.server 8000 -d site
```

Mở:

```text
http://localhost:8000
```

## Test

```sh
python -m compileall scripts
sh tests/smoke.sh
```

Hoặc sau khi chạy server local, mở `http://localhost:8000` bằng trình duyệt.

## Hiệu chỉnh phân trang Kindle

Bộ mẫu tại `/debug/` dùng để đo viewport thật và hiệu chỉnh thuật toán phân trang trên Kindle.
Có thể sinh riêng bộ mẫu mà không gọi website nguồn:

```sh
python scripts/fetch.py --debug-only
python -m http.server 8000 -d site
```

Sau đó mở `http://localhost:8000/debug/`. Bộ mẫu gồm trang thông số trình duyệt và các nhóm
văn xuôi (`P`), thơ (`V`), cấu trúc hỗn hợp (`M`) và ranh giới thanh điều hướng (`B`).

## Deploy GitHub Pages

1. Commit toàn bộ file.
2. Push lên branch `main`.
3. Vào GitHub repo `Settings > Pages`.
4. Chọn `Source = GitHub Actions` nếu chưa chọn.
5. Vào tab `Actions` chạy workflow `Pages` thủ công lần đầu bằng `workflow_dispatch`, hoặc chờ push tự chạy.
6. Mở URL GitHub Pages được workflow trả ra.

Workflow cũng tự chạy hằng ngày lúc 00:05 giờ Việt Nam. Cron UTC tương ứng là `5 17 * * *`.
Mỗi lần tạo site thành công, script chỉ giữ nội dung của hôm qua, hôm nay và ngày mai.

## Debug lỗi parse

Script lưu HTML gốc vào:

- `.cache/source.html`
- `build/source.html`

Nếu GitHub Actions báo lỗi parse, xem log workflow và file debug nói trên trong artifact/log local. Khi không tách được đủ 7 giờ kinh, script vẫn tạo `site/error.html` để đọc nguyên nhân, nhưng trả exit code khác 0 để Actions báo lỗi.
