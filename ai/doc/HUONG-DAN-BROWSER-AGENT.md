# Hướng dẫn sử dụng — browser-agent cho CVAT

Tài liệu này là **hướng dẫn dùng**, tách khỏi `TIEN-DO-BROWSER-AGENT.md` (nhật ký kỹ
thuật + bằng chứng). Đọc file này khi cần **làm việc**; đọc file kia khi cần biết
**vì sao** làm thế và **đã kiểm chứng bằng gì**.

Phạm vi: Face Landmark **VF-50** (50 điểm / 7 nhóm) và HumanPose-**17**.

---

## 1. Chuẩn bị một lần

| Thứ cần | Ở đâu | Ghi chú |
|---|---|---|
| Lõi browser-agent | `D:\browser-agent-core\venv` | có `browser_use 0.13.10`, `mediapipe 0.10.21` (`solutions`), `playwright` |
| Chrome | `C:\Program Files\Google\Chrome\Application\chrome.exe` | dùng cờ sẵn có, không cần cài gói |
| python hệ thống | bất kỳ | chạy `tools/`; **không cài được gì từ PyPI** |
| Tài khoản CVAT online | `cvat.note.transformerlabs.ai` | cần khi ghi lên online |

**Hai điều bắt buộc nhớ:**

1. **Mọi lệnh lái trình duyệt phải chạy NGOÀI sandbox** — Chrome bị sandbox DSH chặn,
   tiến trình thoát ngay với exit `-36863`.
2. **Phạm vi ghi annotation: chỉ job có assignee của bạn.** Kiểm tra bằng
   `python work\my_jobs.py`.

**Về MediaPipe — hai môi trường, hai API.** Máy này có hai bản:

| Python | mediapipe | API dùng | Model |
|---|---|---|---|
| `D:\browser-agent-core\venv` | 0.10.21 | `mediapipe.solutions` | nhúng sẵn trong wheel |
| python hệ thống | 1.0.1 | Tasks API | tải `.task` một lần về `~\.cache\browser-agent\mediapipe` |

Code **tự chọn** đường chạy được, nên cả hai đều suy luận được landmark. Kết quả không
giống nhau tuyệt đối (xem tiến độ mục 2.15) — **khi ghi thật nên dùng một môi trường cố
định**, và payload landmark có trường `api` để biết kết quả đến từ đường nào.

---

## 2. Đổi luật annotation (việc thường gặp nhất)

Luật số (ngưỡng cả-skeleton) là **dữ liệu**, không nằm trong code. Sửa JSON là hành vi
agent đổi ngay — không cần sửa Python, không cần build lại.

```powershell
python tools\check_rules.py              # xem luật đang dùng + tài liệu nguồn ghi gì
#   -> sửa rules\week2-rules.json cho khớp
python tools\check_rules.py --check      # xác nhận hết lệch (exit 0, dùng được trong CI)
```

**Nếu BTC ra guideline mới mà bạn quên sửa JSON**, `--check` sẽ báo:

```
LỆCH 3 chỗ:
  - mattrai: guideline ghi 5/8 nhưng luật đang dùng 4/8
```

Đây chính là cơ chế chống "lệch âm thầm" — trước đây ngưỡng nằm cứng trong
`pipeline.py` nên tài liệu đổi mà agent vẫn chạy số cũ.

**Giới hạn có chủ ý:** agent **không tự sửa** luật từ câu chữ tài liệu. Guideline là
văn xuôi tự do; tự suy ra hành vi từ đó sẽ sai lặng lẽ. Người vẫn là người chốt luật —
agent chỉ **phát hiện** và **báo**.

---

## 3. Đồng bộ sau khi thay tài liệu guideline

```powershell
python tools\sync_all.py --status        # 1. file nguồn nào đã đổi
python tools\sync_all.py                 # 2. đồng bộ guideline + artifact label
python tools\check_rules.py --check      # 3. luật còn khớp tài liệu nguồn không
```

Bước 3 là bước mới và **quan trọng** — đừng bỏ.

Nếu `sync_all` báo có **label mới trong tài liệu**: thêm label đó vào `taxonomy.yaml`
(nguồn sự thật duy nhất cho label), rồi chạy lại bước 2. Pipeline **không tự sửa**
`taxonomy.yaml`, vì tự ghi đè từ văn bản tự do sẽ phá annotation đang có trong CVAT.

Triển khai lại nuclio nếu label đổi: xem `nuclio/README.md` mục 6b.

---

## 4. Suy luận landmark và ghi annotation

### 4.1 Xem thử trước, không ghi (nên làm)

```powershell
# Ảnh trên đĩa, ghi lên CVAT local
python tools\agent_vision.py --task pose17 --image datasets\1354\G01_B011.jpg

# Job trên CVAT online
python tools\agent_online.py --job 2214 --task face50 --frames all
```

Lệnh **luôn in cảnh báo của guideline** (ảnh có thể bị lật, nhóm bị đánh Outside,
không thấy mặt…). **Đọc trước khi tin kết quả.**

### 4.2 Soi bằng MẮT trước khi ghi (bài mặt)

Bảng toạ độ không cho thấy hình, mà reviewer lại nhìn hình. Vì vậy trước khi ghi bài
mặt lên job, hãy dựng ảnh có điểm + đường nối:

```powershell
python tools\preview_face_landmarks.py work\face_2214_f0.jpg --table
```

Ra `<ảnh>_annotated.png` và ba ảnh phóng to mày / mũi / miệng. Mở ảnh, đối chiếu với
guideline mục 3: mày nằm trên bờ trên, sống mũi chạy hết tới chóp, môi ngoài khép vòng
theo viền môi. Bốn lỗi reviewer từng nêu (mày dưới, miệng lệch, mũi ngắn, nối sai) đều
nhìn ra được ở bước này.

### 4.3 Ghi thật

```powershell
# CVAT local, một ảnh
python tools\agent_vision.py --task pose17 --target local --job 26 --image a.jpg --write

# CVAT online, nhiều frame, bỏ qua frame đã có shape
python tools\agent_online.py --job 2214 --task face50 --frames all --write
```

| Tham số | Ý nghĩa |
|---|---|
| `--task pose17` / `--task face50` | chọn bài (17 khớp người / 50 điểm mặt) |
| `--frames all` hoặc `--frames 0,2,4` | nhiều frame (chỉ `agent_online`) |
| `--skip-labelled` | bỏ frame đã có shape (**mặc định BẬT**) |
| `--rotate auto` | tự thử 0/90/180/270, chọn hướng model thấy nhiều khớp nhất |
| `--write` | **không có thì không ghi gì cả** |

**An toàn dữ liệu:** lệnh ghi **append**, không xoá dữ liệu đang có. Lệnh cũng tự chặn
job không giao cho bạn. Đây là lý do job 2218 (đã có pre-label đủ) **không bị đụng**.

---

## 5. Lái CVAT bằng trình duyệt

### 5.1 Cách chính — giao việc cho browser-use

Bạn **mô tả việc bằng lời**; browser-use tự lập kế hoạch, tự bấm, tự đọc trang. LLM
không bấm từng bước. Đây là đường bắt buộc theo yêu cầu hạng mục.

```powershell
python tools\agent_browser_use.py `
  --task "Mở job này và cho tôi biết có bao nhiêu skeleton, liệt kê tên nhóm." `
  --url "https://cvat.note.transformerlabs.ai/tasks/344/jobs/2214"
```

### 5.2 Đổi LLM — không cần sửa code

```powershell
--provider deepseek   --model deepseek-v4-pro      # mặc định
--provider openai     --model gpt-4o
--provider anthropic  --model claude-sonnet-4
--provider google     --model gemini-2.0-flash
--provider ollama     --model qwen2.5              # chạy local, không cần internet
--provider litellm    --model bedrock/anthropic.claude-v2
```

Provider hỗ trợ sẵn: `deepseek`, `openai`, `anthropic`, `google`, `groq`, `ollama`,
`openrouter`, `mistral`, `litellm`. **`litellm` bao hơn 100 nhà cung cấp khác** mà
không phải viết thêm nhánh nào. Provider lạ thì báo lỗi rõ kèm gợi ý — không âm thầm
rơi về mặc định.

Hoặc dùng biến môi trường: `BROWSER_USE_PROVIDER`, `BROWSER_USE_MODEL`,
`BROWSER_USE_BASE_URL`, `BROWSER_USE_API_KEY`.

> ⚠️ **Đừng dùng `deepseek-flash` cho browser-use.** browser-use ép `tool_choice` ở
> bước trả kết quả, mà DeepSeek từ chối `tool_choice` ép buộc khi thinking bật. Server
> của `flash` luôn bật thinking và client không tắt được → agent chạy vài bước rồi chết
> ở bước "Result". Dùng `deepseek-v4-pro`. Chi tiết: `TIEN-DO-BROWSER-AGENT.md` mục 2.3.

### 5.3 Dùng phiên Chrome đã đăng nhập

```powershell
# 1. Mở Chrome kèm cổng debug (đóng hết Chrome trước)
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
    --remote-debugging-port=9222 `
    --user-data-dir="$env:LOCALAPPDATA\Google\Chrome\User Data"
# 2. Đăng nhập CVAT bằng tay trong cửa sổ đó
# 3. Giao việc, chỉ vào phiên đó
python tools\agent_browser_use.py --task "..." --url "..." --cdp-url http://127.0.0.1:9222
```

Không copy cookie sang profile khác được: Chrome khoá cookie bằng
`app_bound_encrypted_key`, chỉ đúng chrome.exe với đúng profile gốc giải mã được.

### 5.4 Cách dự phòng — CDP trực tiếp

Chỉ dùng khi cần **đúng một thao tác cụ thể** (dump DOM, chụp ảnh). Đây không phải
đường chính.

```powershell
python tools\agent_browser.py --url http://localhost:8080/api/server/about --dom --expect 2.74.1
python tools\agent_browser.py --url http://localhost:8080/ --shot D:\anh\ui.png   # dùng đường dẫn tuyệt đối
python tools\agent_browser.py --attach                                            # gắn vào Chrome đang mở
```

---

## 6. Lấy token CVAT online khi `.env` hỏng

```powershell
# 1. Mở Chrome kèm cổng debug (như mục 5.3)
# 2. Đăng nhập và lưu token THẬT vào work/online_token.txt
python work\online_session.py --login --username <user>
python work\online_session.py --whoami       # kiểm tra token còn sống
```

⚠️ **Gia hạn một token đã có không làm nó hợp lệ trở lại — phải TẠO TOKEN MỚI.** Cách
trên lấy token thật qua phiên đăng nhập, nên không phải vào UI CVAT tạo tay.

⚠️ `work/online_token.txt` chứa token **có quyền ghi** lên CVAT online. Xoá ngay khi xong
— bản cũ đã được xoá trong đợt dọn dẹp (xem mục 2.16 của file tiến độ).

---

## 7. Kiểm chứng lại hệ thống

Chạy khi nghi ngờ, hoặc sau khi sửa code:

```powershell
python -m pytest test\ -q                  # toàn bộ test (hiện 127 passed)
python work\verify_skeleton_write.py       # định dạng payload skeleton (tự tạo task tạm rồi dọn)
python work\e2e_vision_write.py            # suy luận thật -> ghi thật
python work\check_vf50_rerun.py            # MediaPipe thật -> map_face50 -> 5 bất biến guideline
python work\prove_tests_catch_old_bugs.py  # test mới có THẬT SỰ bắt lỗi cũ không
python work\prove_evidence_tests_catch_old_bug.py  # dẫn chứng guideline: thuật toán cũ hỏng, mới đúng
python work\diag_skeleton_evidence.py      # soi dẫn chứng bộ sinh chọn cho từng điểm skeleton
python work\compare_mediapipe_apis.py      # lệch giữa mediapipe 0.10.21 và 1.0.1
python work\rule_drift_probe.py            # luật có bắt được lệch khi nguồn đổi
python tools\agent_probe.py --target local --job 7   # token, schema, annotation
python tools\agent_docker.py               # container nào của ai, rác còn gì
```

### 7.1 Soi 50 điểm bằng mắt — làm mỗi lần đổi code landmark

Đây là cách duy nhất phát hiện "điểm gắn đúng nhưng nối sai": bảng toạ độ không cho
thấy hình, mà hình mới là thứ reviewer nhìn.

```powershell
python tools\preview_face_landmarks.py work\face_2214_f0.jpg --table
```

Ghi ra `<ảnh>_annotated.png` (50 điểm + đường nối, mỗi nhóm một màu) và ba ảnh phóng to
`_zoom_brow`, `_zoom_nose`, `_zoom_mouth`. Dòng đầu in ra **API MediaPipe đang dùng**, để
biết kết quả đến từ đường nào.

### 7.2 Bất biến guideline trên ảnh thật

`work\check_vf50_rerun.py` chạy **đúng** `MediaPipeRunner` + `map_face50` mà pipeline
dùng, rồi kiểm 5 bất biến rút từ guideline. Kết quả mong đợi:

```
mục 3.1/5.2 (x của 0..9 tăng dần)      ĐẠT
mục 3.3 (mí trên cao hơn mí dưới)      ĐẠT
mục 3.3 (contour mắt không tự cắt)     ĐẠT
mục 3.4 (moitrong nằm trong moingoai)  ĐẠT
mục 3.2 (4 điểm sống mũi chia đều)     ĐẠT — tổng dài ~55.9px
```

Chạy được bằng **cả hai** python: venv lõi (`solutions`, 0.10.21) và python hệ thống
(Tasks, 1.0.1):

```powershell
& 'D:\browser-agent-core\venv\Scripts\python.exe' work\check_vf50_rerun.py
python work\check_vf50_rerun.py
```

Hai đường lệch nhau ≤35px ở pose và ≤7.8px ở mặt (xem tiến độ mục 2.15), nên **khi ghi
thật nên dùng một môi trường cố định**. Payload landmark nay có trường `api` ghi rõ
kết quả đến từ đường nào.

### 7.3 Bài HumanPose-17 — kiểm trái/phải

```powershell
& 'D:\browser-agent-core\venv\Scripts\python.exe' work\pose_axis_probe.py
```

`pose_axis_probe.py` kiểm 8 cặp khớp hai bên có đúng phía khung hình không. **Lưu ý:**
`pose_verify_final.py` (bảng 44/56/100%) đã bị **rút lại** — nó quét bộ ảnh test của dự
án chứ không phải ảnh task, và dòng tính điểm cho chiến lược C đếm vô điều kiện nên luôn
ra 100%. Đừng dùng nó làm bằng chứng. Xem tiến độ mục 2.13.

`rule_drift_probe.py`, `check_vf50_rerun.py` và `pose_axis_probe.py` là ba thứ đáng chạy
nhất sau khi đụng vào luật hoặc hình học — chúng kiểm cái mà test tổng hợp **không** kiểm
được.

---

## 8. Xử lý sự cố nhanh

| Triệu chứng | Nguyên nhân thường gặp | Xử lý |
|---|---|---|
| Chrome thoát ngay, exit `-36863` | Đang chạy trong sandbox | Chạy lại **ngoài sandbox** |
| "đã chụp" mà không thấy file ảnh | Đường dẫn tương đối ghi vào cwd của Chrome | Dùng đường dẫn **tuyệt đối** |
| Agent chạy vài bước rồi chết ở "Result" | Đang dùng `deepseek-flash` | Đổi sang `deepseek-v4-pro` |
| `400 Thinking mode does not support...` | Như trên | Như trên |
| Mở trang CVAT online thấy form "Sign in" | Chưa có phiên đăng nhập | Dùng `--cdp-url` vào Chrome đã đăng nhập |
| `check_rules --check` báo lệch | Tài liệu nguồn đổi, JSON chưa | Sửa `rules/week2-rules.json` |
| `sync_guidelines.py` báo `DEEPSEEK_API_KEY not set` | `.env` thiếu key | Không chặn — đối chiếu luật đọc thẳng docx |
| `PermissionError` khi xoá file trong `guildlline/` | File mang cờ ReadOnly | `chmod(0o666)` trước khi xoá |
| Ghi annotation bị chặn | Job không giao cho bạn | `python work\my_jobs.py` để xem phạm vi |
| Cảnh báo "hai bên gần như trùng trục ngang" | Mặt/người nhìn thẳng, không phân được trái/phải | Bình thường — điểm đó giữ nhãn model, soi lại bằng mắt |
| `... không còn API 'solutions'` | mediapipe 1.x đã bỏ API cũ | **Không cần làm gì** — code tự chuyển sang Tasks API |
| Lần đầu chạy báo không tải được `face_landmarker.task` | Máy chặn mạng | Tải thủ công rồi đặt `BROWSER_AGENT_MEDIAPIPE_MODEL_DIR` trỏ tới thư mục chứa model |
| Điểm nằm sai chỗ / nối sai hình | Code landmark vừa bị sửa | `python tools\preview_face_landmarks.py <ảnh>` rồi **nhìn ảnh** |
| Kết quả khác nhau giữa hai lần chạy | Hai python dùng hai bản mediapipe khác nhau | Xem tiến độ mục 2.15 — dùng một môi trường cố định khi ghi thật |
| Khớp tay/chân đặt sai chỗ dù trái/phải đúng | MediaPipe thấy kém ở vùng bị ghế che (visibility < 0.35) | Luật đánh Outside cho điểm dưới ngưỡng — điểm đó không nên có toạ độ |
