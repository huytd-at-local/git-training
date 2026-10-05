# Kindle GKPv Static Site

Static site tối giản để đọc Các Giờ Kinh Phụng Vụ trên Kindle Paperwhite browser cũ.

Nguồn nội dung: <https://ktcgkpv.org/readings/prayer> và
<https://ktcgkpv.org/readings/mass-reading>

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

Cả ba mode Tiếng Việt (Kindle, Responsive và Monastic Breviary) có 7 giờ kinh
và mục thứ 8 **Bài đọc Thánh lễ**, đặt sau Kinh Tối. Các mục cùng bao gồm hôm qua,
hôm nay và ngày mai theo giờ Việt Nam. Bài đọc Thánh lễ giữ các phần nguồn cung cấp:
Ca nhập lễ, Bài đọc 1, Đáp ca, Bài đọc 2 nếu có, Tung hô Tin Mừng, Tin Mừng và Ca hiệp lễ.
Build lấy bộ lễ và từng bản bài đọc mặc định khi mở trang nguồn; nếu có nhiều lựa
chọn, chỉ dùng lựa chọn đầu tiên như nguồn. Bài đọc giữ nguyên văn, trích dẫn và
số câu, với tên lễ riêng của bộ đọc đã chọn.

Đường dẫn hôm nay là `/bai-doc-thanh-le.html`,
`/bai-doc-thanh-le-responsive.html` và `/breviary/bai-doc-thanh-le.html`;
các ngày khác dùng thư mục ngày như những giờ kinh hiện có. Kindle và Breviary
phân trang cùng nội dung; Responsive hiển thị trọn bài trên một trang.
Nếu tải hoặc đọc dữ liệu Thánh lễ thất bại, build dừng trước khi ghi các trang mới;
workflow không deploy và giữ website đã xuất bản.

Bản tiếng Anh được mã hóa nằm tại `/breviary/en/` và chỉ được sinh khi có biến
`BREVIARY_EN_PASSCODE` gồm đúng sáu chữ số. GitHub Actions đọc giá trị này từ
secret cùng tên; passcode không được ghi vào website hoặc repository. Để chỉ
sinh lại phần tiếng Anh ở local:

```sh
BREVIARY_EN_PASSCODE=123456 .venv/bin/python scripts/fetch.py --english-only
```

Chế độ học tiếng Anh có bản phân trang Kindle tại `/breviary/en/learner/`
và bản responsive không phân trang tại `/breviary/en/learner-responsive/`.
Hai bản dùng cùng nội dung hôm nay: cột trái giữ nguyên câu tiếng Anh từ nguồn,
cột phải là IPA British RP sinh local bằng eSpeak NG 1.52.0, voice `en-GB-x-rp`.
Khi sinh các trang learner tiếng Anh, eSpeak NG 1.52.0 phải có sẵn dưới tên
`espeak-ng` trên PATH; build kiểm tra phiên bản trước khi sinh IPA. Actions dùng
Ubuntu 26.04 và cài eSpeak NG từ package Ubuntu. Không cần API hay cache phiên âm;
Kindle chỉ nhận HTML mã hóa đã tạo sẵn.
Reading và cả hai bản learner được sinh trong cây staging rồi thay thế cùng nhau.
Nếu nguồn iBreviary hoặc build lỗi, workflow giữ toàn bộ bản English thành công
gần nhất từ Pages artifact và tiếp tục publish phần tiếng Việt, với warning
trong GitHub Actions.

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

Workflow chạy hằng ngày lúc 00:23 và 01:17 giờ Việt Nam; cron UTC lần lượt
là `23 17 * * *` và `17 18 * * *`. GitHub có thể chạy cron trễ. Lượt 01:17 là
một cơ hội phục hồi nếu nguồn hoặc build tạm thời lỗi. Mỗi build English thành
công sinh lại learner local cho hôm nay; Reading vẫn gồm hôm qua, hôm nay và ngày mai.

## Debug lỗi parse

Script lưu HTML gốc vào:

- `.cache/source.html`
- `build/source.html`

Nếu GitHub Actions báo lỗi parse, xem log workflow và file debug nói trên trong artifact/log local. Khi không tách được đủ 7 giờ kinh hoặc không lấy được Bài đọc Thánh lễ, script vẫn tạo `site/error.html` để đọc nguyên nhân, nhưng trả exit code khác 0 để Actions báo lỗi.
