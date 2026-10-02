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

Chế độ **Monastic Breviary** dành cho Kindle nằm tại:

```text
http://localhost:8000/breviary/
```

Nếu chỉ cần sinh lại chế độ này từ các trang hiện có mà không tải dữ liệu mới
hoặc thay đổi root:

```sh
python scripts/fetch.py --breviary-only
```

Bản tiếng Anh được mã hóa nằm tại `/breviary/en/` và chỉ được sinh khi có biến
`BREVIARY_EN_PASSCODE` gồm đúng sáu chữ số. GitHub Actions đọc giá trị này từ
secret cùng tên; passcode không được ghi vào website hoặc repository. Để chỉ
sinh lại phần tiếng Anh ở local:

```sh
BREVIARY_EN_PASSCODE=123456 .venv/bin/python scripts/fetch.py --english-only
```

Chế độ học tiếng Anh nằm tại `/breviary/en/learner/`. Nó chỉ được sinh khi có
thêm `BREVIARY_LEARNER_GEMINI_API_KEY`; Gemini API chỉ chạy lúc build để tạo phiên âm
IPA Anh-Anh tự nhiên và giải thích từ đơn giản. Kindle chỉ nhận HTML mã hóa đã tạo sẵn,
không gọi API hay tải tài nguyên ngoài lúc đọc. GitHub Actions giữ cache ngắn
hạn của kết quả ngôn ngữ để tránh tạo lại các câu lặp. Model mặc định là
`gemini-3.7-flash`. Nếu Gemini trả thiếu một mục, build giữ ngay các mục hợp lệ
và retry riêng phần còn thiếu. Nếu learner hoặc nguồn iBreviary vẫn lỗi,
workflow giữ bản English đã deploy thành công gần nhất và tiếp tục publish phần
tiếng Việt; lỗi phụ vẫn xuất hiện dưới dạng warning trong GitHub Actions.
Lượt dự phòng tự phục hồi learner nếu thiếu ngày hiện tại; nếu đã có thì tái sử dụng
bản mã hóa, không gọi Gemini. Actions summary báo ngày yêu cầu, ngày có sẵn và
trạng thái refresh/reuse/fallback riêng cho hai bản learner.
Client giới hạn tổng cộng 4 request / 60 giây trong mỗi lượt, gồm retry HTTP,
repair và fallback, để giữ khoảng đệm dưới quota 5 RPM của các model Flash
production được xác nhận trong AI Studio ngày 02/10/2026. Đây không phải bộ
đếm RPD: project Free tier hiện có 20 request/ngày/model, dùng chung giữa các
key và các lượt manual/qualification. Giảm RPM không khắc phục lỗi upstream 503.
Nếu model chính hết retry do lỗi server/kết nối tạm thời, biến
`BREVIARY_LEARNER_FALLBACK_MODELS` cho phép chuyển lần lượt sang model dự phòng
cho phần còn lại của lượt. Actions giữ chuỗi `gemini-3.7-flash` → `gemini-3.6-flash`
→ `gemini-3.5-flash`, chỉ đi một chiều và không quay lại model đã lỗi;
không chuyển model khi lỗi xác thực, request sai hoặc quota 429. Ngân sách mỗi
lượt sinh ngôn ngữ là 15 phút / 120 request, dùng chung cho toàn bộ chuỗi model.
Job `learner-freshness` kiểm tra artifact độc lập; có thể báo đỏ vì learner cũ
trong khi job deploy Reading vẫn thành công.

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
văn xuôi (`P`), thơ trong một stanza (`V`), thơ đúng cấu trúc HTML production (`R`), trang do
thuật toán phân trang mới chọn (`A`), cấu trúc hỗn hợp (`M`) và ranh giới thanh điều hướng (`B`).

### Mô phỏng Kindle trong Chrome DevTools

Trong DevTools, bật **Device Toolbar**, chọn **Edit > Add custom device** rồi dùng:

- Tên: `Kindle Paperwhite 3 - GKPv`
- Viewport: `1072 x 1268` CSS pixels
- Device pixel ratio: `1.7964`
- Device type: `Desktop (touch)`
- User agent: `Mozilla/5.0 (X11; ; U; Linux armv7l; en-us) AppleWebKit/534.26+ (KHTML, like Gecko) Version/5.0 Safari/534.26+`

Chọn thiết bị vừa tạo và để mức zoom của Device Toolbar ở `Fit`. Dùng chiều cao `1268`
(kích thước `document.client` đã đo), không dùng toàn bộ chiều cao màn hình `1448` vì phần
giao diện trình duyệt Kindle chiếm phần còn lại. DPR chủ yếu giúp JavaScript và ảnh chụp gần
với thiết bị; kích thước `1072 x 1268` mới là thông số quyết định việc xuống dòng.

Đây là mô phỏng gần đúng để phát hiện trang tràn và thanh điều hướng bị đẩy khỏi viewport.
Chrome vẫn dùng rendering engine hiện đại nên kết quả cuối cùng phải được xác nhận trên Kindle.

## Deploy GitHub Pages

1. Commit toàn bộ file.
2. Push lên branch `main`.
3. Vào GitHub repo `Settings > Pages`.
4. Chọn `Source = GitHub Actions` nếu chưa chọn.
5. Vào tab `Actions` chạy workflow `Pages` thủ công lần đầu bằng `workflow_dispatch`, hoặc chờ push tự chạy.
6. Mở URL GitHub Pages được workflow trả ra.

Workflow chạy hằng ngày lúc 00:23, 01:17 và 15:23 giờ Việt Nam; cron UTC lần lượt
là `23 17 * * *`, `17 18 * * *` và `23 8 * * *`. GitHub có thể chạy cron trễ.
Lượt 00:23 buộc refresh learner; hai lượt dự phòng và `Run workflow` thủ công
dùng `missing`, chỉ sinh lại nếu thiếu ngày hiện tại hoặc profile đã cũ.
Push lên `main` không buộc sinh learner. Recovery 15:23 nằm sau thời điểm reset
RPD lúc nửa đêm Pacific cả PST lẫn PDT, tạo thêm cơ hội phục hồi khi hai lượt
ban đêm gặp 503; không bảo đảm dịch vụ sẽ sẵn sàng hoặc còn đủ quota.
Mỗi lần tạo site thành công, script chỉ giữ nội dung của hôm qua, hôm nay và ngày mai.

## Debug lỗi parse

Script lưu HTML gốc vào:

- `.cache/source.html`
- `build/source.html`

Nếu GitHub Actions báo lỗi parse, xem log workflow và file debug nói trên trong artifact/log local. Khi không tách được đủ 7 giờ kinh, script vẫn tạo `site/error.html` để đọc nguyên nhân, nhưng trả exit code khác 0 để Actions báo lỗi.
