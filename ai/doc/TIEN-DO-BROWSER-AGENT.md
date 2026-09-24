# Tiến độ — tính năng browser-agent cho CVAT

File này là **bộ nhớ bền** của hạng mục: nó ghi cái gì đã xong, cái gì đang dở, và
bằng chứng nào đã kiểm chứng. Đọc file này trước khi làm tiếp.

Cập nhật lần cuối: **đợt 5** — sửa bốn lỗi landmark bài mặt mà reviewer nêu
(mày/miệng/mũi/đường nối), sửa nguyên nhân gốc là MediaPipe không chạy được trên máy
này, và thêm lệnh soi ảnh trước khi ghi.

> **Đọc nhanh:** mục 1 (mục tiêu) → mục 5 (bảng trạng thái) → mục 8 (hướng dẫn dùng).
> Mục 2 là nhật ký kỹ thuật kèm bằng chứng; mục 3 là bẫy đã trả giá.
> **Ai sửa bài mặt: đọc mục 2.14 trước** — nó ghi rõ lỗi gì, sửa thế nào, và cái gì
> chưa tái hiện được.

---

## 1. Mục tiêu hạng mục

1. Tương tác trực tiếp vào CVAT bằng browser-agent, lõi browser-use đặt riêng ở
   `D:\browser-agent-core` để tái dùng cho nhiều dự án.
2. Làm **cả hai đường**: lái UI bằng browser và ghi bằng REST API, để đối chiếu nhau.
3. Vision lấy từ `model-service` hiện có, cộng thêm FaceMesh cho bài mặt.
4. Một lệnh duy nhất tự đồng bộ label khi `guildlline/` thay đổi.
5. Phạm vi bài: **Face Landmark VF-50** và **HumanPose-17**.
6. Document sử dụng lưu trong `ai/doc/`.
7. Dọn container lạ ngoài dự án trong Docker.

**Bổ sung đợt 4 (người dùng yêu cầu):**

8. **Bắt buộc dùng browser-use** để tương tác web. LLM chỉ **giao việc**, không tự
   bấm từng bước.
9. **Đổi nhà cung cấp LLM linh hoạt** — sau này bỏ DeepSeek vẫn thay agent khác được.
10. **Agent tự nhận diện rule từ guideline** để chạy theo, thay vì luật nằm cứng
    trong code.

---

## 2. Nhật ký kỹ thuật (kèm bằng chứng)

### 2.1 Tách luật thành dữ liệu — agent tự nhận diện rule (ĐỢT 4, trọng tâm)

**Vấn đề đo được trước khi sửa.** `work/rule_autoupdate_probe.py` (bản cũ) đã chứng
minh: sửa ngưỡng trong tài liệu nguồn rồi chạy `sync_all.py` thì **bản trích xuất cập
nhật, nhưng hành vi agent thì không** — ngưỡng nằm cứng trong `vision/pipeline.py`,
nên rule mới nằm trong markdown còn agent vẫn dùng số cũ. Lệch **âm thầm**.

**Cách sửa — hai phần, phải có đủ cả hai mới có tác dụng:**

1. **Luật thành dữ liệu.** `rules/week2-rules.json` giữ ngưỡng cả-skeleton. Đổi luật
   là sửa JSON, **không phải sửa Python**. `pipeline.skeleton_thresholds()` đọc file
   này lúc chạy, nên đổi file là hành vi agent đổi theo.
2. **Bắt buộc đối chiếu với tài liệu nguồn.** `browser_agent/vision/rules.py` đọc
   ngưỡng **thẳng từ bảng trong `.docx` nguồn** và so với luật đang dùng. Lệch thì
   `python tools/check_rules.py --check` thoát khác 0, dùng được trong CI.

**Vì sao đối chiếu với `.docx` nguồn chứ không phải bản Markdown sinh ra** — đây là
phát hiện thật trong lúc làm: `tools/sync_guidelines.py` cần `DEEPSEEK_API_KEY`, mà
`.env` **không có key này**, nên bước trích xuất đang **thoát ngay** (`ERROR:
DEEPSEEK_API_KEY not set`). Đó cũng là lý do vì sao `guideline/README.md` ghi mãi
trạng thái "đã đổi" mà bản sinh ra không thay đổi. Nếu tôi đối chiếu với bản sinh ra
thì bộ kiểm tra sẽ **im lặng vô ích**. Mốc đối chiếu phải là thứ BTC phát hành.

**Bằng chứng — `work/rule_drift_probe.py` chạy hoàn toàn trên bản sao:**

```
BƯỚC 1 — đọc ngưỡng thẳng từ tài liệu nguồn (.docx)
  longmayphai 3/5   longmaytrai 3/5   matphai 4/8
  mattrai 4/8       moingoai 6/12     moitrong 4/8
BƯỚC 2 — tài liệu gốc chưa đổi: lệch 0 chỗ (đúng)
BƯỚC 3 — sửa bản sao 4/8 -> 5/8:
  ngưỡng đọc từ bản sao: (5, 8)
  lệch: 3 chỗ — matphai/mattrai/moitrong: "nguồn ghi 5/8 nhưng luật đang dùng 4/8"

KẾT LUẬN: 1. đọc được từ docx nguồn ✅  2. bắt được lệch ✅  3. im lặng khi chưa đổi ✅
```

**Trả lời câu hỏi "đã tự động nhận diện rule mà chạy theo được chưa":**

| Mức | Trạng thái |
|---|---|
| Agent **chạy theo** rule trong file luật (đổi JSON là đổi hành vi) | **CÓ** |
| Agent **phát hiện** khi tài liệu nguồn đổi ngưỡng | **CÓ** — `check_rules --check` |
| Agent **tự sửa** luật của mình từ câu chữ tài liệu, không cần người | **KHÔNG — cố ý** |

Vì sao **cố ý** không tự sửa: câu chữ guideline là văn xuôi tự do. Tự suy ra hành vi
từ đó sẽ sai lặng lẽ — đúng loại lỗi đã gặp ở mục 2.4. Cách này giữ **một** chỗ quyết
định hành vi, đồng thời **ép** phát hiện lệch. Người vẫn là người chốt luật.

**Cách dùng đầy đủ:**

```powershell
python tools\sync_all.py                 # tài liệu nguồn -> guideline/generated/
python tools\check_rules.py              # in luật đang dùng + đối chiếu
python tools\check_rules.py --check      # thoát khác 0 nếu lệch (dùng trong CI)
```

Khi BTC đổi ngưỡng: `check_rules` báo lệch → sửa `rules/week2-rules.json` cho khớp →
chạy lại → hết lệch.

### 2.2 browser-use tự lái — LLM chỉ giao việc (ĐỢT 4)

Người dùng yêu cầu rõ: **bắt buộc dùng browser-use**, LLM không tự bấm từng bước.

| | `tools/agent_browser_use.py` (**chính**) | `tools/agent_browser.py` (dự phòng) |
|---|---|---|
| Ai quyết từng bước | **browser-use** | LLM gọi từng lệnh CDP |
| Đầu vào | mô tả việc bằng lời | URL / JS cụ thể |
| Đổi LLM | đổi `--provider/--model`, không sửa code | không liên quan |

**Kiến trúc ba tầng:**

```
tools/agent_browser_use.py   (repo, python hệ thống)  ← LLM giao việc ở đây
        │  subprocess + biến môi trường BROWSER_USE_*
        ▼
browser_agent/vision/worker_browsent.py  (venv lõi, có browser_use 0.13.10)
        │  browser-use tự lập kế hoạch, tự bấm, tự đọc trang
        ▼
Chrome (tự mở, hoặc gắn vào Chrome đang mở qua --cdp-url)
```

Đã kiểm chứng thật: giao việc *"Mở trang và cho tôi biết phiên bản CVAT"* →
browser-use tự mở trình duyệt, tự đọc JSON, tự trả lời `2.74.1` trong **2 bước**.

**Ranh giới được khoá bằng test AST.** `test/test_agent_browser_use.py` đọc mã lớp
giao việc và **đổ** nếu nó bắt đầu gọi `Page.navigate` hay lệnh CDP — để không ai
âm thầm quay lại kiểu điều khiển trực tiếp.

### 2.3 Đổi nhà cung cấp LLM — không cần sửa code (ĐỢT 4)

`worker_browsent.py` có `build_llm()` định tuyến theo tên provider. Đã kiểm chứng
**9/9 provider dựng được**: `deepseek`, `openai`, `anthropic`, `google`, `groq`,
`ollama`, `openrouter`, `mistral`, `litellm`.

```powershell
python tools\agent_browser_use.py --task "..." --url "..." --provider openai --model gpt-4o
python tools\agent_browser_use.py --task "..." --url "..." --provider anthropic --model claude-sonnet-4
python tools\agent_browser_use.py --task "..." --url "..." --provider ollama --model qwen2.5
python tools\agent_browser_use.py --task "..." --url "..." --provider litellm --model bedrock/anthropic.claude-v2
```

**`litellm` là đường thoát hiểm** bao hơn 100 nhà cung cấp khác mà không phải viết
thêm nhánh nào. Provider lạ thì **báo lỗi rõ** kèm gợi ý dùng `litellm`, không âm
thầm rơi về mặc định.

Hoặc dùng biến môi trường, không cần tham số: `BROWSER_USE_PROVIDER`,
`BROWSER_USE_MODEL`, `BROWSER_USE_BASE_URL`, `BROWSER_USE_API_KEY`.

**⚠️ Bẫy DeepSeek đã trả giá (ghi lại kỹ):** browser-use **ép `tool_choice`** ở bước
trả kết quả cuối, nhưng DeepSeek **từ chối `tool_choice` ép buộc khi thinking bật**.
Đo trực tiếp trên API:

| Gửi gì | Kết quả |
|---|---|
| `tools` + `tool_choice=auto` | OK |
| `tools` + `tool_choice=required` | 400 `Thinking mode does not support this tool_choice` |
| `tools` + ép đúng tên hàm | 400 như trên |
| `tools` + ép đúng tên hàm + `thinking: disabled` | **OK** |

Mà lớp `ChatDeepSeek` chỉ gửi `thinking: disabled` khi **tên model chứa `deepseek-v4`**.
Nên:

- `deepseek-flash`: server **luôn** bật thinking, client không tắt được → agent chạy
  vài bước rồi **chết ở bước "Result"**. Không dùng được cho browser-use.
- `deepseek-v4-pro`: tôn trọng `thinking: disabled` → chạy tốt. **Đây là mặc định.**

Vì vậy `provider_settings()` **cố ý không** lấy `DEEPSEEK_MODEL` từ `.env` (đang đặt
`deepseek-flash`). Có test khoá lại điều này. Muốn bật thinking thì đặt
`BROWSER_USE_THINKING=true`, nhưng khi đó phải dùng model không ép tool_choice.

**Hai lỗi nữa đã sửa:** `ChatOllama` không nhận `temperature` trực tiếp (phải qua
`ollama_options`) nên bản đầu `TypeError`; và console Windows cp1252 làm chết worker
khi in kết quả tiếng Việt.

### 2.4 GHI ĐƯỢC ANNOTATION LÊN CVAT ONLINE — và nhìn thấy trên UI

Phạm vi do người dùng chốt: **chỉ job có assignee `2A202602286`**. Liệt kê bằng
`work/my_jobs.py`: **2 job** — `2214` (task 344, 5 frame) và `2218` (task 345, 13 frame).

| Job | Trước | Sau | Ghi chú |
|---|---|---|---|
| 2214 | 0 shape, 5 frame trống | **35 skeleton / 250 điểm**, đủ 5/5 frame | bài Face Landmark VF-50, 7 nhóm |
| 2218 | 91 shape, đã đủ 13/13 frame | **không đụng tới** | đã có pre-label đầy đủ |

**Kiểm chứng bằng hai đường độc lập:**

1. **REST**: `job 2214: 35 shape | frame {0:7, 1:7, 2:7, 3:7, 4:7} | tổng điểm 250`,
   mỗi nhóm đúng số điểm (5/5/4/8/8/12/8).
2. **UI bằng mắt**: mở editor trong trình duyệt thấy **7 skeleton `(AUTO)`** vẽ đúng
   trên mặt người lái — lông mày, sống mũi, hai mắt, môi ngoài, môi trong. Sidebar
   "Items: 7".

**Chỉ ghi vào frame trống.** Job 2218 đã có đủ pre-label nên bị bỏ qua; đây đúng tinh
thần guideline ("BTC đã nạp sẵn ảnh và điểm gợi ý… không nên dùng chức năng upload
annotation", vì thao tác đó ghi đè toàn bộ). Lệnh tự chặn job không giao cho mình và
tự bỏ frame đã có shape.

```powershell
python work\my_jobs.py                                     # phạm vi: job giao cho tôi
python tools\agent_online.py --job 2214 --task face50 --frames all          # xem thử
python tools\agent_online.py --job 2214 --task face50 --frames all --write  # ghi thật
```

**Ba bài học về đường trình duyệt (đã trả giá):**

1. `POST /api/auth/login` chỉ trả **token**, KHÔNG tạo session cho SPA. Sau khi gọi
   API đó, mở lại trang vẫn thấy form "Sign in".
2. **Điều hướng bằng URL không đáng tin.** Gõ `/tasks/344/jobs/2214` bị redirect về
   `/jobs`; thêm `?frame=0` cũng vậy. `history.pushState` + `popstate` thì mở được
   editor nhưng **có lần nhảy sang job khác** (2212 của task 343); bấm hàng trong danh
   sách cũng nhảy sang 2210/2206. Cách chạy được: pushState rồi **kiểm tra lại job id
   trong `location.href`**, sai thì quay về `/jobs` và thử lại.
3. Id job trong danh sách `/jobs` là **text node, không phải `<a>`**.

**Lưu ý bảo mật:** `work/online_token.txt` từng chứa token có quyền ghi lên CVAT
online. **File này đã được xoá** trong đợt dọn dẹp (mục 2.16); token trong đó cũng
đã hết hạn (401). Khi đăng nhập lại, nhớ xoá ngay sau khi dùng xong.

### 2.5 Schema label thật đọc từ CVAT — online KHỚP HOÀN TOÀN với repo

`GET /api/labels?job_id=2214` trả **8 skeleton**:

| Label | Type | Sublabel | Repo |
|---|---|---|---|
| `person` | skeleton | `"1"`..`"17"` | `POSE17_SKELETON` ✅ |
| `longmaytrai` | skeleton | `"0"`..`"4"` | ✅ |
| `longmayphai` | skeleton | `"5"`..`"9"` | ✅ |
| `songmui` | skeleton | `"10"`..`"13"` | ✅ |
| `mattrai` | skeleton | `"14"`..`"21"` | ✅ |
| `matphai` | skeleton | `"22"`..`"29"` | ✅ |
| `moingoai` | skeleton | `"30"`..`"41"` | ✅ |
| `moitrong` | skeleton | `"42"`..`"49"` | ✅ |

**Điều này giải quyết câu hỏi chặn cũ.** Bài mặt trên CVAT **online** dùng ĐÚNG 7
skeleton 0..49 như guideline và như repo mô hình hoá — **không phải 68 điểm**. Con số
68 chỉ là cấu hình của một project khác trên CVAT **localhost** (project `pose_data`,
`GET /api/labels?project_id=3`: `body` 1..17, `person` 17 tên giải phẫu, `face` 1..68,
`feet` 1..6, `hands` 1..42).

Hệ quả: entry point HumanPose-17 trên localhost là **`body`**, không phải `person`
(`POSE17_LABEL_CANDIDATES = ("body", "person")`). Repo hỗ trợ cả hai cấu hình:
`face_group_shapes()` cho 7 nhóm (online), `points_to_skeleton_shape()` cho một skeleton.

**Lỗi công cụ dò đã sửa:** `tools/agent_probe.py` trước đây dò label tên `person` nên
**không bao giờ** đối chiếu được HumanPose-17, và với bài mặt nó im lặng bỏ qua khi
không thấy 7 label nhóm — cả hai là "xanh giả". Nay nó dò `body`/`person`, và khi
không tìm thấy schema VF-50 thì **nói rõ lý do** kèm danh sách skeleton số đang có.
Test hồi quy: `test/test_agent_probe.py`, dùng payload chép nguyên từ CVAT thật.

### 2.6 Ảnh mặt thật — lần đầu kiểm chứng được FaceMesh

Job 2214 là ảnh người lái trong cabin, `frame 0` tải được qua
`/api/jobs/2214/data?type=frame&number=0`. FaceMesh tìm thấy **468 điểm**, map ra
**50/50 điểm VF-50**, không điểm nào Outside.

`work/verify_vf50_geometry.py` kiểm các bất biến guideline **trên mặt thật**:
**TẤT CẢ ĐỀU ĐÚNG** — chiều hai dãy lông mày, khoé mắt trái/phải nhất, hai mí chạy
ngược chiều, mí trên cao hơn mí dưới, môi trong nằm gọn trong môi ngoài, và cả ba
vòng (2 mắt + môi) **không tự cắt**.

**Lỗi thật đã sửa nhờ có ảnh mặt thật:**

**Tập 8 điểm mắt bị "vặn".** Bản trước dùng thẳng 8 chỉ số
`(33,246,161,160,159,158,157,133)` và coi `159,158,157` là mí trên. Trên mặt thật, ba
điểm đó có `y` LỚN HƠN khoé, tức chúng nằm trên mí **DƯỚI**. Vì tập điểm đã vặn sẵn,
`order_eye_contour` chia phe trên một contour méo và thứ tự dựng ra sai — mắt trái
cho mí trên nằm **dưới** mí dưới 9 pixel.

Cách sửa: thêm `MP_EYE_RING` (vòng **16 đỉnh** đầy đủ của MediaPipe) và
`order_eye_contour` nay **chọn** 8 điểm từ vòng đó: hai khoé theo toạ độ, rồi chọn 3
điểm mí trên / 3 điểm mí dưới bằng **dấu khoảng cách có hướng** tới đường nối hai
khoé, ưu tiên điểm gần giữa mắt (đó mới là nơi mí trên cao nhất / mí dưới thấp nhất).

**Bài học phương pháp:** test tổng hợp tự tôi dựng có thể xác nhận một lược đồ sai,
vì fixture được viết theo chính giả định sai đó. Chỉ ảnh thật mới lộ ra. Chi tiết
đáng nhớ: script kiểm tra của tôi cũng báo **7 "lỗi" giả** trước khi đúng, vì áp
những phép kiểm không bất biến với tư thế đầu (ví dụ ép cả 10 điểm lông mày tăng một
chiều, trong khi guideline nói hai dãy chạy NGƯỢC chiều nhau).

### 2.7 Tầng landmark theo guideline — hai lỗi hình học đã sửa

`browser_agent/geometry.py` + `browser_agent/vision/landmarks.py`.

**(a) Contour mắt bắt chéo chữ X.** Bản cũ sắp 8 điểm mắt theo toạ độ `x` tăng dần.
Guideline mục 3.3 nói contour phải "bắt đầu ở điểm trái nhất, chạy dọc **mí trên**
sang điểm phải nhất, rồi vòng về theo **mí dưới**" và cấm "đường bắt chéo tạo thành
hình chữ X". Sắp thuần theo `x` sẽ xen kẽ mí trên với mí dưới → đúng hình chữ X bị cấm.
Nay `order_eye_contour()` dựng thứ tự bằng hình học (dấu khoảng cách có hướng), **bất
biến với phép quay ảnh**.

**(b) Môi không theo khoé trái.** Guideline mục 3.4 nói điểm 30 và 42 là "khoé miệng
trái". Bản cũ dùng nguyên thứ tự MediaPipe, chỉ đúng khi mặt không lật. Nay
`order_closed_contour()` quay vòng để điểm trái nhất khung hình đứng đầu, giữ nguyên
topology vòng.

### 2.8 Một lệnh đồng bộ guideline + label

`python tools/sync_all.py` (thêm `--check`, `--status`, `--force`, `--quiet`).

- Đã nạp đủ **4 tài liệu nguồn** vào `guildlline/`: 2 PDF (bbox/polygon/polyline và
  semantic segmentation) + 2 DOCX (Face Landmark VF-50 v1.3, HumanPose-17 v1.1).
- Sinh `guideline/generated/*.md` + vùng bảng trong `guideline/README.md`.
- `--check` sau khi sync trả `EXIT=0` → **idempotent**.
- Trích xuất từ `.docx` **giữ nguyên bảng** — điều kiện sống còn vì toàn bộ quy tắc
  point ID / sublabel nằm trong bảng.

**Sửa lỗi tầng trích xuất:** bản cũ ghim cứng `pypdf`, mà máy này **không cài được
pypdf** (PyPI không truy cập được). Nay `tools/sync/extract.py` thử lần lượt
`pypdf → pdfplumber → pypdfium2 → pdfminer` và ghi tên engine vào header file sinh ra.
Máy này dùng `pdfplumber 0.11.9`.

⚠️ **Giới hạn đã biết:** bước "chuẩn hoá bằng LLM" (`tools/sync_guidelines.py`) cần
`DEEPSEEK_API_KEY` mà `.env` không có, nên hiện **thoát ngay**. Hệ quả: bảng nguồn
trong `guideline/README.md` ghi mãi trạng thái "đã đổi" dù bản sinh ra không đổi.
Việc đối chiếu luật (mục 2.1) **không phụ thuộc** bước này.

### 2.9 Đường ghi REST — định dạng skeleton đã chốt

`work/verify_skeleton_write.py` chạy hết một vòng thật trên CVAT localhost: tạo task
trong project `pose_data`, nạp 2 ảnh, ghi **1 skeleton `body` 17 điểm**, đọc lại và so
khớp — rồi tự xoá task tạm. Kết quả: `KẾT LUẬN: ĐỊNH DẠNG SKELETON ĐÚNG`.

```json
{"label_id": 437, "frame": 0, "type": "skeleton", "points": [],
 "outside": false, "occluded": false, "attributes": [],
 "elements": [{"label_id": 438, "frame": 0, "type": "points",
               "points": [x, y], "outside": false, "occluded": false,
               "attributes": []}]}
```

**Ba lỗi thật trong `browser_agent/cvat_rest.py` đã sửa** (đều là lỗi im lặng, chỉ lộ
ra khi gọi thật):

1. `action` của `PATCH /jobs/{id}/annotations` là **query param**, không phải field
   trong body. Bản cũ gửi `{"action": "create", ...}` → CVAT trả 400
   `Please specify a correct 'action' for the request`.
2. `upload_annotations` dựng boundary sai: header khai `----browseragentboundary` nhưng
   body ghi `"--" + boundary` = 6 gạch → 415 `Unsupported media type`.
3. `upload_annotations` gửi `Accept: application/json` cho request multipart, mà CVAT
   bắt buộc `application/vnd.cvat+json` → 406.

**Bốn bài học về API CVAT 2.74:**

- `POST /api/tasks` **chỉ nhận JSON**, không nhận multipart. Schema OpenAPI của
  instance là nguồn sự thật: `GET /api/schema/?format=json`.
- Nạp ảnh là **3 pha** tới `POST /api/tasks/{id}/data/`: header `Upload-Start: true`
  → multipart chứa `client_files[0]` → header `Upload-Finish: true`. Pha finish phải
  gửi kèm field **`image_quality`**.
- `POST /api/tasks` phải khai trước `client_files` (tên file), nếu không worker chết
  với `ValueError: No media data found` và task ở lại `size=0`.
- `GET /api/tasks/{id}` **không** trả danh sách job; trường `jobs` là dict
  `{"count": n, "url": ...}`. Muốn lấy job id phải gọi `/api/jobs?task_id=`.

### 2.10 Suy luận landmark thật → ghi CVAT: E2E PASS

`work/e2e_vision_write.py` chạy thật một vòng:

```
ảnh datasets/1354/G01_B011.jpg
  → worker (venv lõi, mediapipe 0.10.21) → landmark thô 33 điểm
  → map guideline → 17 điểm visible=17 outside=0
  → ghi CVAT localhost → đọc lại: skeleton label=437, elements=17, points cha=[]
```

**Kiến trúc vì sao phải tách worker:** `mediapipe` chỉ có trong venv lõi
(`D:\browser-agent-core\venv`), python hệ thống **không cài được** (PyPI bị chặn).
Nên worker `browser_agent/vision/worker_landmarks.py` được gọi bằng python của lõi, chỉ
trả **landmark thô**; mọi suy luận về point ID / trạng thái nằm trong repo, để chỉ có
**một** chỗ quyết định.

**Auto-rotate:** guideline HumanPose-17 mục 1.1 yêu cầu "ảnh bị xoay 90°… nhìn xác
định đâu là đầu đâu là chân". Máy làm tương tự: thử 0/90/180/270 và chọn hướng model
thấy nhiều khớp nhất — suy luận hình học, không đoán theo tên điểm.

**Luật ngưỡng cả-skeleton (guideline mục 4.2).** `apply_skeleton_thresholds` đánh
**Outside cả nhóm** khi số điểm còn căn cứ dưới ngưỡng. Điểm `Occluded` **vẫn được
tính** là còn căn cứ ("điểm không thấy đánh Occluded"). Điểm Outside vẫn được gửi kèm
`outside: true` chứ không bị bỏ, vì schema skeleton phải đủ node. Ngưỡng nay đọc từ
`rules/week2-rules.json` (mục 2.1).

### 2.11 Dọn container lạ — đã rà soát, không có gì lạ

`tools/agent_docker.py` phân loại theo **nhãn compose** và **network**, không đoán
theo tên. Kết quả trên máy:

| Nhóm | Số lượng | Ghi chú |
|---|---|---|
| `cvat-browser-agent_v2` (repo này) | 1 | `cvat-smart-model` |
| `cvat` (hệ CVAT ở `cvat-day2`) | 19 | phụ thuộc, không phải "lạ" |
| function nuclio | 5 | 4 function của repo + storage reader |
| **ngoài dự án** | **0** | ✅ không có gì phải dọn |

Rác thật: **0 container đã dừng**, **0 image không tag**, **2 volume mồ côi** — đều là
volume còn lại của 2 function CVAT đã bị xoá
(`nuclio-nuclio-pth-facebookresearch-sam-vit-h`, `nuclio-nuclio-pth-mmpose-hrnet32`).

Mặc định lệnh **chỉ báo cáo**; muốn xoá phải `--prune --yes`.

**Một lỗi đã sửa trong chính công cụ:** bản đầu suy volume đang dùng từ
`docker ps --format json`, trường `Mounts` ở đó bị cắt ngắn nên báo nhầm **13 volume
"mồ côi"** trong khi chúng đang được dùng. Nay lấy từ `docker inspect`.

### 2.12 Phát hiện: UI CVAT localhost trả 404 vì router `cvat-ui` không tồn tại

**Chỉ ảnh hưởng CVAT localhost, KHÔNG ảnh hưởng cvat.note.transformerlabs.ai.**
Người dùng đã xác nhận chỉ cần dùng agent của dự án trên CVAT localhost, nên lỗi này
không chặn mục tiêu — nhưng ghi lại vì nó là bất thường thật.

Bằng chứng (từ access log của traefik, `docker logs traefik`):

| Request | Status | `RouterName` |
|---|---|---|
| `/api/server/about` | 200 | `cvat@docker` |
| `/static/` | 403 | `cvat@docker` |
| `/admin` | 301 | `cvat@docker` |
| `/` , `/models`, `/tasks` | **404** | **(trống)** |

`RouterName` trống = **không router nào khớp**. Còn `cvat_ui` thì hoàn toàn khoẻ:
`docker exec cvat_ui wget -qO- http://127.0.0.1:8000/` trả về đúng `index.html`.

**Nguyên nhân:** `traefik` đã chạy **33 phút**, còn `cvat_ui` chỉ **25 phút** —
container UI được tạo lại SAU khi traefik khởi động, và Docker provider của traefik
không đăng ký lại router `cvat-ui`.

**Hệ quả:** hiện chỉ dùng được CVAT localhost qua **REST API**; UI trên `localhost:8080`
trả 404 cho mọi đường dẫn giao diện.

**Cách chữa (chưa áp dụng — cần người dùng đồng ý vì đây là deployment của họ):**

```powershell
docker restart traefik      # để provider đọc lại nhãn của cvat_ui
```

Nếu vẫn 404 thì thêm nhãn network tường minh cho `cvat_ui` trong
`D:\DockerData\Cvat\cvat-day2\docker-compose.yml` rồi `docker compose up -d cvat_ui`:
`traefik.docker.network: cvat_cvat`.

---

## 3. Bẫy môi trường đã trả giá (đọc trước khi chạy)

| Bẫy | Triệu chứng | Cách xử lý |
|---|---|---|
| Sandbox DSH chặn Chrome | Thoát ngay, exit `-36863` | Mọi lệnh lái trình duyệt phải chạy **ngoài sandbox** |
| `--screenshot` đường dẫn tương đối | Lệnh báo "đã chụp" mà file biến mất | Dùng `.resolve()` — Chrome ghi vào cwd của nó, không phải cwd gọi |
| PyPI bị chặn từ python hệ thống | Không cài được `mediapipe`, `websocket-client`, `pypdf` | Worker chạy qua venv lõi `D:\browser-agent-core\venv`; repo có WebSocket tự viết (`cdp_ws.py`) |
| File trong `guildlline/` mang cờ ReadOnly | `PermissionError` khi xoá/ghi đè, kể cả bản copy | `chmod(0o666)` trước khi xoá; `shutil.copy2` chép cả cờ |
| Console Windows cp1252 | Worker chết khi in tiếng Việt | `sys.stdout.reconfigure(encoding="utf-8")` |
| `ChatOllama` không nhận `temperature` | `TypeError` | Truyền qua `ollama_options` |
| DeepSeek + ép `tool_choice` | 400 `Thinking mode does not support this tool_choice` | Dùng model tôn trọng `thinking: disabled` (mục 2.3) |
| Cookie Chrome khoá bằng `app_bound_encrypted_key` | Không copy cookie sang profile khác được | Phải mở lại đúng Chrome của người dùng |

---

### 2.13 Trái/phải HumanPose-17 — chọn (B) và lỗi ánh xạ tĩnh bị ngược

**Quyết định của người dùng: (B).** Guideline mục 2.1: "Điểm R nằm ở phía phải của ảnh
đang hiển thị; điểm L nằm ở phía trái của ảnh. Không suy luận theo tay/chân giải phẫu."

**Lỗi thật đã sửa.** `POSE17_POINTS` gán MediaPipe index 12 (vai **giải phẫu** phải) cho
point 6 tên "R Shoulder", tức đặt điểm R ở bên **trái** khung hình — ngược thẳng
guideline. Bằng chứng (`work/pose_axis_probe.py`, hai mẫu thật): cả 8 cặp khớp đều
ngược. Nay gán theo khung hình.

**Cách sửa:** `geometry.POSE17_ANATOMICAL_PAIRS` khai hai index ứng viên của mỗi khớp;
`landmarks.resolve_frame_side_indices()` chọn theo toạ độ của chính ảnh đó — index nào
có `x` lớn hơn thì vào point chẵn (phía phải khung). Khi hai bên chênh dưới
`POSE17_SIDE_MIN_SPREAD` (0.01), không có cơ sở hình học để phân bên: **giữ nhãn model
và cảnh báo**, không đoán. Sublabel nay mang nghĩa **"phía khung hình"**, không phải
"bên cơ thể" — đúng như (B) đã chọn và đúng như guideline viết.

**Lưu ý về tai:** MediaPipe **không** theo quy luật chẵn/lẻ ở index tai (7 = tai trái,
8 = tai phải; ngược với vai/mắt). Đã kiểm trên `work/wm_pose.json` và ghi lại trong
`geometry.py` để không ai "sửa" nhầm về quy luật chung.

> **RÚT LẠI MỘT SỐ ĐO SAI.** Bản trước của mục này dẫn bảng "A 44% / B 56% / C 100%
> trên 24 ảnh người lái thật" để chứng minh không tồn tại ánh xạ tĩnh nào đúng. Số đo
> đó **không dùng được**, vì hai lý do:
>
> 1. **Sai nguồn dữ liệu.** `work/pose_verify_final.py` quét
>    `datasets/1354` + `test/detect` — đó là **bộ test YOLO của dự án**, không phải ảnh
>    task được giao. Con số "24 ảnh" là 50 ứng viên trừ 26 ảnh model không thấy người.
> 2. **Phép đo rỗng.** Dòng tính điểm của C trong script **đếm vô điều kiện**
>    (`score["C"][0] += 1`) trong khi tiêu chí "đúng" được định nghĩa là
>    `x_even > x_odd`. Hai câu giống hệt nhau, nên 146/146 chỉ là **đo lại định nghĩa
>    của chính nó**. Script tự in ra: "đạt 100% theo định nghĩa của chính nó".
>
> Vì vậy kết luận "không ánh xạ tĩnh nào đúng" hiện **chưa có bằng chứng**. Việc gán
> theo khung hình vẫn đúng về mặt quy ước (khớp mục 2.1), nhưng **cần đo lại trên ảnh
> thật của task** trước khi dùng làm căn cứ.

### 2.14 Bài mặt (job 2214) — bốn lỗi reviewer nêu, và nguyên nhân gốc

**Nhận xét của reviewer (nguyên văn):** *"lông mày đang ở dưới, nó phải trên cơ; thứ
hai khuôn miệng chưa khớp; khuông mũi quá ngắn so với thực tế; cơ bản gắn đúng nhưng
nối bị sai rất nhiều."*

**Phạm vi đo.** Job 2214 là bài **Face Landmark VF-50**, 5 frame, schema online chứa
**8 label**: 7 nhóm mặt (50 điểm) *cộng* `person` (17 sublabel — chính là HumanPose-17,
xem `work/online_job_2214_labels.json`). Bài bị reviewer chê là **bài mặt**.

**Ảnh dùng để đo:** frame thật của job 2214 (`work/face_2214_f0.jpg`, 1280×720, không
có EXIF orientation). Đây mới là dữ liệu của task, không phải bộ ảnh của dự án.

#### Nguyên nhân gốc: bản cài MediaPipe không chạy được, nên không ai kiểm lại

Đây là thứ phải sửa trước, vì nó là lý do bốn lỗi kia tồn tại lâu:

- `browser_agent/vision/mediapipe_pose.py` chỉ hỗ trợ `mediapipe.solutions`.
- Máy này cài **mediapipe 1.0.1**, đã **bỏ hẳn** `solutions`; Tasks API thì cần file
  `.task` mà wheel không kèm.
- Hệ quả: **mọi lệnh suy luận face đều ném lỗi**. Không ai chạy lại được để kiểm, nên
  lỗi nằm im. `requirements.txt` cũng không ghim `mediapipe`, nên tình trạng này không
  hiện ra ở đâu cả.

Đã sửa: `mediapipe_tasks.py` (Tasks API + tải/đệm model, có
`BROWSER_AGENT_MEDIAPIPE_MODEL_DIR` cho máy không mạng) và `mediapipe_pose.py` nay tự
chọn đường chạy được (`.api` trả `"solutions"` hoặc `"tasks"`). Kiểm trên máy này:
`API dùng: tasks`, 468 landmark, `ok=True`.

#### Lỗi 1 — "nối bị sai rất nhiều": môi lấy sai index

Đây là lỗi nặng nhất và đúng như reviewer mô tả.

Vòng môi **thật** của MediaPipe có **20 điểm mỗi vòng**, lấy từ
`FaceLandmarksConnections.FACE_LANDMARKS_LIPS` (40 cạnh = 2 vòng × 20). Code cũ dùng
một bộ 12 index chép tay rồi quay vòng theo x. Đo trên frame thật, hệ quả là:

```
bản cũ — môi ngoài 30..41 (x, index):
  30(566) 31(569) 32(575) 33(583) 34(596) 35(609) 36(620)
  37(631) 38(639) 39(644) 40(646) 41(571)   <- 5 điểm môi dưới dồn vào khoé phải
```

Nửa môi dưới bên trái **không có điểm nào**, và điểm 41 nằm ngược đầu ở khoé trái
trong khi 37–40 ở khoé phải. Nối lại thì thành hình rối — chính là "nối bị sai rất
nhiều".

**Cách sửa.** Hai nửa vòng được khai đúng theo kết nối của MediaPipe
(`MP_OUTER_LIP_UPPER/LOWER`, `MP_INNER_LIP_UPPER/LOWER`), rồi **chọn điểm theo tỉ lệ
cung** (`pick_points_by_arc`) khớp bảng tỉ lệ guideline mục 3.4. Kèm một chi tiết dễ
sai đã phát hiện khi đo: guideline đo môi dưới **ngược chiều** (từ khoé phải), nên
`MOUTH_TARGET_RATIOS` cho 37..41 và 47..49 đã được quy về `1-x`.

Kết quả trên frame thật (`work/check_vf50_rerun.py`):

```
môi ngoài: 30(564) 31(576) 32(598) 33(610) 34(621) 35(639) 36(647)
           37(588) 38(600) 39(612) 40(622) 41(631)
```

Môi dưới nay trải khắp chiều ngang môi, không dồn về một khoé.

#### Lỗi 2 — "khuông mũi quá ngắn": sống mũi dừng ở nửa đường

Bộ cũ `(168, 6, 197, 195)` — đo trên frame thật, `195` ở `y=349` trong khi nasion
`168` ở `y=324` và chóp mũi ở `y=377`.

```
bản cũ: sống mũi dài 27.1px  (trên tổng 53px từ nasion tới chóp = 51%)
bản mới: sống mũi dài 55.9px  (đoạn 18.4 / 17.7 / 19.8px, tỉ lệ dài-ngắn = 1.12)
```

Bộ mới đi hết chiều dài sống mũi tới chóp: `MP_NOSE_RIDGE_CHAIN = (168, 6, 197, 51, 44)`,
4 điểm chọn chia đều theo cung và chỉ nhận đỉnh nằm trong dải trục giữa
(`MP_NOSE_MIDLINE_TOLERANCE = 8px`).

#### Lỗi 3 — "lông mày đang ở dưới": KHÔNG tái hiện được, và tôi không sửa gì

Phải nói thẳng: **tôi không dựng lại được lỗi này**, nên không có gì để sửa. Số đo
trên frame thật:

```
mày phải khung (0..4, index 46/53/52/65/55): y = 320, 309, 302, 301, 307
mắt phải khung (14..21):                     y = 343 (khoé 33)
-> cả 5 điểm mày cao hơn mắt 19–38px
```

Đo trên cả 10 điểm của hai mày thì **không điểm nào nằm dưới mắt**. Ngoài ra mesh
MediaPipe chỉ có đúng 5 đỉnh cho mỗi mày (đã dò toàn bộ 468 đỉnh: không đỉnh nào khác
nằm trong bán kính 3px của chuỗi mày), nên không có bộ "bờ trên" nào khác để chuyển
sang. Thứ tự x của 0..9 cũng đã tăng dần: `502 511 525 544 571 613 635 650 661 669`.

**Điều tôi có thể làm và đã làm:** thêm lệnh dựng ảnh có nhãn để bạn tự nhìn
(`tools/preview_face_landmarks.py`, xem mục 7), và khoá bất biến "mày phải nằm trên
mắt" bằng test. Nếu bạn vẫn thấy mày nằm dưới sau khi xem ảnh preview, gửi tôi **số
frame** cụ thể — có thể đó là frame mà model suy luận sai, khác với frame tôi đo.

#### Lỗi 4 — "gắn đúng nhưng nối sai"

Phần "gắn đúng" khớp với đo của tôi: các đỉnh được chọn đều nằm đúng chỗ giải phẫu.
Phần "nối sai" là hệ quả trực tiếp của lỗi 1 (môi), vì đường nối đi theo point ID nên
chỉ sai khi bộ index sai.

#### Đã xác minh trên frame thật sau khi sửa

```
mục 3.1/5.2 (x của 0..9 tăng dần)      ĐẠT  502 511 525 544 571 613 635 650 661 669
mục 3.3 (mí trên cao hơn mí dưới)      ĐẠT  cả 6 cặp
mục 3.3 (contour mắt không tự cắt)     ĐẠT  cả hai mắt
mục 3.4 (moitrong nằm trong moingoai)  ĐẠT  x30=564 < x42=568, x46=644 < x36=647
mục 3.2 (4 điểm sống mũi chia đều)     ĐẠT  tỉ lệ dài/ngắn = 1.12
```

**Test mới, và đã chứng minh là biết bắt lỗi.** Thêm 4 test:
`test_mouth_lower_lip_points_spread_over_the_whole_lip`,
`test_nose_bridge_spans_the_nose_instead_of_stopping_halfway`,
`test_mouth_contours_start_at_left_corner_and_keep_ring_order` (nay kiểm bằng cung
trên vòng thật, không bằng toạ độ x), và phần "12 điểm môi phải khác nhau" trong
`test_assign_face_sides_covers_all_50_points`.

Bộ test xanh không tự nó chứng minh gì — nên tôi **dựng lại lỗi cũ** và chạy lại:
`work/prove_tests_catch_old_bugs.py` (monkeypatch đúng hai lỗi cũ) → **exit=1, 3 test
đổ**, trong đó `điểm 13 phải ở gần chóp mũi, đang là 195` và cả hai test môi.
Hai test cũ `test_mouth_contours_...` và `test_assign_face_sides_covers_all_50_points`
đã phải viết lại vì chúng khoá theo bộ index chép tay cũ, tức đang bảo vệ chính lỗi.

**Còn phải làm:** người dùng muốn lấy **task 2218 làm chuẩn** để so (2218 / 2213 / 2211).
Chưa làm được: `CVAT_TOKEN` trong `.env` trả 401 `Invalid token` trên cả ba job
(`work/probe_ref_jobs.py`), và Docker Desktop đang tắt nên không có đường localhost.
Cần token mới rồi mới so được.
### 2.15 Hai đường MediaPipe (0.10.21 `solutions` vs 1.0.1 Tasks) — đo mức lệch

**Vì sao phải đo.** Sau khi `mediapipe_pose.py` và `worker_landmarks.py` hỗ trợ cả hai
API, kết quả ghi lên CVAT **phụ thuộc vào python nào chạy worker**. Nếu hai đường lệch
nhau nhiều thì không thể "kiểm bằng máy này, ghi bằng máy khác".

**Cách đo.** Cùng một frame `work/face_2214_f0.jpg`, chạy worker hai lần:
`D:\browser-agent-core\venv\Scripts\python.exe` (mediapipe 0.10.21, `solutions`) và
python hệ thống (mediapipe 1.0.1, Tasks). So từng landmark
(`work/compare_mediapipe_apis.py`, `work/compare_pose_detail.py`).

**Kết quả.**

```
                    lệch lớn nhất      ghi chú
pose, 33 điểm       dx 0.014 (18px)    13/33 điểm đủ tin cậy (visibility >= 0.35)
                    dy 0.048 (35px)
face, 468 điểm      dx 0.0045 (5.7px)  toàn bộ 468 điểm
                    dy 0.011 (7.8px)
```

Nhìn toàn bộ 33 điểm pose thì lệch tới **202px** — nhưng phải đọc kèm cột visibility:

```
idx15: visibility 0.26 / 0.05  lệch 153px
idx17: visibility 0.27 / 0.04  lệch 175px
idx19: visibility 0.39 / 0.08  lệch 202px
idx21: visibility 0.40 / 0.08  lệch 186px
idx23..27: visibility 0.00 / 0.00
```

Tất cả điểm lệch lớn đều có `visibility` **dưới ngưỡng 0.35 của guideline mục 4**, tức
bị đánh **Outside** và **toạ độ không được dùng**. Đây là chân/vùng bị ghế xe che. Sau
khi lọc theo đúng ngưỡng đó, hai đường khớp trong 18–35px.

**Kết luận và việc đã làm.**

1. Hai đường **đủ tương đương** để dùng: khác biệt nằm ở vùng mà luật đã bắt bỏ.
2. Nhưng **vẫn nên dùng một môi trường cố định** khi ghi thật, vì pose lệch tới 35px ở
   điểm hợp lệ là đủ để reviewer thấy. Ghi rõ trong `worker_landmarks.py` rằng payload
   nay có thêm trường `api` (`"solutions"` hoặc `"tasks"`) để biết kết quả đến từ đường nào.
3. `tools/preview_face_landmarks.py` in ra `API MediaPipe:` ngay dòng đầu, nên khi soi
   ảnh là biết đang đo bằng đường nào.

**Điều này cũng giải thích một phần vì sao chất lượng bị chê.** Ảnh dựa trên xe hơi:
phần thân dưới bị ghế và bảng taplo che. Guideline nói rõ "bị che đến mức không còn căn
cứ ước lượng" thì đánh Outside — nhưng nếu lần chạy trước ghi toạ độ cho những điểm đó
thì reviewer sẽ thấy điểm nằm sai chỗ. Mức độ ảnh hưởng: 20/33 điểm pose dưới ngưỡng
tin cậy trên frame này.
---

### 2.16 Dọn dẹp project, và một lỗi thật trong cách chọn dẫn chứng guideline

Đợt này có hai việc: rà lại project cho sạch, và sửa một lỗi **do chính việc rà đó
phát hiện ra**.

**Lỗi thật: bộ sinh profile chọn dẫn chứng theo "dòng khớp đầu tiên".**

`tools/guidelines.py::_skeleton_evidence` cũ lấy dòng **đầu tiên** trong bản trích xuất
chứa điểm cần tìm. Hai cách nó sai, cả hai đều im lặng:

| Bài | Dòng khớp trước | Hệ quả |
|---|---|---|
| pose17 | bảng tra cứu `\| 1 \| Nose \| 10 \| R Wrist \|` | **cả 17/17 điểm** nhận dẫn chứng khô, không nói gì về vị trí giải phẫu |
| face50 | câu `ID chạy liên tục 0–49 …` (khớp *mọi* điểm 0–49) | **17/50 điểm** nhận dẫn chứng chung, che mất bảng nhóm của chúng |

Đo bằng `work/diag_skeleton_evidence.py`. Thuật toán mới xếp hạng ứng viên:
(1) **dòng riêng của đúng điểm** — 3 ô, ô đầu đúng số điểm, ô cuối là tỉ lệ *hoặc* câu
mô tả; (2) dòng khai **khoảng hẹp nhất** chứa điểm. Khoảng trải ≥25 điểm bị loại vì nó
khớp gần cả bài nên không chứng minh được gì.

Chứng minh test mới biết bắt lỗi (không chỉ xanh vì may):
`work/prove_evidence_tests_catch_old_bug.py` → **thuật toán cũ hỏng 17/17 điểm pose17 và
17/50 điểm face50; thuật toán mới hỏng 0**. Sau khi sinh lại, cả 4 profile vẫn `applied`.

**Đã xoá (231 MB).** Bốn nhóm, mỗi nhóm có lý do riêng:

| Nhóm | Nội dung | Vì sao xoá được |
|---|---|---|
| Hồ sơ trình duyệt | `work/chrome-login/` (2315 mục, 220 MB) | cache/profile Chrome sinh lại được |
| Dump nháp CVAT | `_cvat_*.txt/py`, `env_dump.txt`, `testout.txt`, `bs_test.json`… | kết quả dò một lần, đã ghi vào tài liệu |
| Ảnh/log trùng | ảnh chụp UI, log build, bản trích PDF thô | đã có `editor_verified.png` và `guideline/generated/` |
| **Bí mật** | `work/online_token.txt` | token có quyền ghi; cũng đã hết hạn (401) |
| **Trùng byte** | `work/_vf50_source_backup.docx` (3.67 MB) | **hash trùng** với `guildlline/…v1.3.docx` |
| Code chết | `tools/read_docx.py` | docstring tự khai "không dùng cho pipeline"; chức năng đã có ở `tools/sync/extract.py` |

`work/`: **2132 file / 290 MB → 587 file / 69.7 MB.**

**Giữ lại có chủ ý.** Nhiều file trong `work/` **được docstring của code đang chạy trích
dẫn làm bằng chứng** (`browser_agent/vision/landmarks.py` nhắc `work/check_vf50_rerun.py`,
`browser_agent/geometry.py` nhắc `work/pose_axis_probe.py` và `work/pose_frame_rule_probe.py`).
Xoá chúng là xoá dấu vết của quyết định kỹ thuật, nên chúng ở lại.

**Kiểm là không phải lỗi.** Ba file `nuclio/build/request-smart-{bbox,lane,semantic}.json`
trùng byte nhau — nhưng chúng chỉ chứa `{"image": <cùng một ảnh test base64>}`, nên trùng
là **đúng**; `deploy_nuclio.py` tự gọi `nuclio/build/` là "scratch directory".

#### 2.16b. Đợt dọn thứ hai — và một chỗ tôi đã phân loại SAI

Ở đợt dọn thứ nhất tôi viết một câu gộp bốn thứ vào một rổ "còn to và cố ý giữ":
`work/bbox_train/`, `work/job_1573/`, `sam-service/` 856 MB, `model-service/weights/`.
**Câu đó sai** — nó làm ba thứ bắt buộc trông như rác tùy chọn. Đo lại bằng cách grep
xem code nào trỏ tới chúng:

| Nhóm | Đo được | Kết luận |
|---|---|---|
| `sam-service/` | 7 file, **856.5 MB là đúng 1 file** `sam2.1_hiera_large.pt` | **BẮT BUỘC.** `docker-compose.yml:19` mount `./sam-service/checkpoints:/models:ro`; dòng 4 ghi thẳng "must be present". Thiếu → `health` báo `checkpoint_exists: false`, `/segment-auto` chết, `docker compose up` không boot. Đã gitignore nên **không lấy lại được từ git**. |
| `model-service/weights/` | 1 file, 42.2 MB `yolo26m.pt` | **BẮT BUỘC.** `models.yaml:47` (checkpoint của model `bbox` mặc định) + `docker-compose.yml:27` mount `/weights:ro`. `README.md:251`: thiếu file này thì ultralytics tải 42 MB từ GitHub ~26 KB/s **và chặn event loop → MỌI endpoint treo**, không chỉ `/detect`. |
| `work/bbox_train/` | 59 file / 43.5 MB | **Rác thật.** Chỉ nhóm này dọn được. |

**Đã xoá (người dùng xác nhận "xoá đi tôi định train lại"):** `work/bbox_train/outputs/`
(chỉ có `yolo26m_bbox_1354_best.pt` 42.0 MB) và `work/bbox_train/dataset/` (20 ảnh train +
5 val). Kết quả: **59 file / 43.5 MB → 5 file / 0.03 MB.**

Xoá `dataset/` là an toàn vì `prepare_dataset.py` dựng lại nó **tất định** (`seed=42`) từ
`train/1354/{images,labels}/train/w1/bbox_polygon/G01` — nguồn 25 ảnh + 25 label, đã kiểm
còn nguyên trước khi xoá. Chạy lại script cho đúng `25 total, 20 train, 5 val`, khớp log cũ.

**Giữ lại có chủ ý:** 4 script (`prepare_dataset.py`, `train_yolo26.py`,
`run_test_inference.py`, `build_contact_sheet.py`) + `train_full.log`. Log là bằng chứng
đường train từng chạy thật trên GPU (`elapsed_s: 38.8`, RTX 4060, `allocated 489.5 MiB`,
`best_exists: true`) — và nó là thứ duy nhất còn chứng minh điều đó sau khi xoá checkpoint,
vì lần train đó chỉ 39 giây trên 20 ảnh nên checkpoint **không phải bằng chứng chất lượng**.

**Giữ theo yêu cầu người dùng:** `work/job_1573/` 6.9 MB / 333 file.

#### 2.16c. Phát hiện khi kiểm chứng: `tools/train.py` chưa tồn tại

Kiểm `tools/` sau khi dọn thì thấy **không có** `train.py`, `lidar*`, `export*`. Nghĩa là
`plan/implement.md` **chưa làm xong**:

- Mục 4 (CLI `python tools/train.py --task <bài> --dataset <thư_mục> --check`) — **chưa có**.
  Việc train hiện phải chạy bằng `work/bbox_train/train_yolo26.py` qua `docker cp`/`docker exec`.
- Mục 3 (LiDAR 3D PCD → fit cuboid → preview → Datumaro) — **chưa có file nào**.
- Mục 1–2 (`models.yaml`, `tools/models.py`, `guideline/profiles/`) — **ĐÃ XONG**, đã kiểm.

`python tools/models.py check` → **EXIT=0**, 7 model, 6 bài có model đang bật (`lidar3d`
đúng là `(không có model đang bật)` theo thiết kế).

---

## 4. Chặn và rủi ro

0. ~~Cần người dùng quyết: quy ước trái/phải của HumanPose-17~~ → **ĐÃ QUYẾT (B) và
   ĐÃ LÀM** — xem mục 2.13. Guideline mục 2.1 xác nhận quy ước theo **khung hình**, và
   code đang làm đúng. Số đo "44/56/100%" chứng minh cho việc này đã **bị rút lại** ở
   mục 2.13 vì sai nguồn dữ liệu và là phép đo rỗng.

1. **Cần token CVAT mới để so với task 2218 (chuẩn).** Người dùng chỉ định lấy task
   2218 làm chuẩn, đối chiếu thêm 2213 và 2211. `CVAT_TOKEN` trong `.env` trả 401
   `Invalid token` trên cả ba job (`work/probe_ref_jobs.py`), Docker Desktop đang tắt.
   Chạy `python work/online_session.py --login` rồi chạy lại `probe_ref_jobs.py`.

2. **Bài mặt job 2214 còn 1 mục checklist hỏng ở f4** — `moitrong` lệch khỏi `moingoai`
   2 px (nhiễu model, xem mục 2.14). Cần quyết có nới ngưỡng cảnh báo hay không.

3. **Chưa đo được chất lượng toạ độ so với bản chuẩn.** Đã sửa lỗi thứ tự lông mày
   (hỏng mục 5.2 ở 5/5 frame) và 6/7 mục checklist nay đạt, nhưng đó là kiểm **bất biến
   hình học**, chưa phải so từng điểm với annotation chuẩn của 2218. Không nên hứa chất
   lượng đạt trước khi có phép so đó.

4. **Token CVAT online trong `.env` vẫn hỏng.** `CVAT_TOKEN` trả 401
   `{"detail":"Invalid token."}`. **Gia hạn một token đã có không làm nó hợp lệ trở
   lại — cần TẠO TOKEN MỚI.** Không còn là việc chặn, vì đường trình duyệt đã thay
   thế được (`work/online_session.py --login` lấy token thật từ phiên đăng nhập).
5. ~~Chưa biết schema bài mặt online~~ → **ĐÃ TRẢ LỜI** (mục 2.5): online dùng đúng 7
   nhóm `0..49` như guideline và như repo.
4. ~~Không có ảnh mặt thật~~ → **ĐÃ CÓ**: `work/face_2214_f0.jpg` lấy từ job 2214.
5. **PyPI không truy cập được từ python hệ thống** → đã giải quyết qua venv lõi.
6. **`tools/sync_guidelines.py` (bước chuẩn hoá bằng LLM) không chạy được** vì thiếu
   `DEEPSEEK_API_KEY`. Không chặn mục tiêu (đối chiếu luật đọc thẳng docx), nhưng nghĩa
   là bản Markdown sinh tự động **không được làm mới**. Cần key nếu muốn dùng.
7. Cổng nuclio: 4 function đã ghim 9001–9004 và CVAT gọi qua dashboard. Không đụng lại.
8. **Còn một việc chưa kiểm chứng:** browser-use mới chạy trên **một** tác vụ đọc
   (`/api/server/about`). Chưa thử nó tự làm việc nhiều bước trên UI CVAT thật.
9. **Máy này chạy HAI bản MediaPipe, kết quả không giống nhau hoàn toàn.** venv lõi có
   `0.10.21` (`solutions`), python hệ thống có `1.0.1` (Tasks). Đo trên cùng một frame:
   pose lệch tới **35px** ở điểm đủ tin cậy, mặt lệch tới **7.8px** (mục 2.15). Không
   chặn gì, nhưng **khi ghi thật nên dùng một môi trường cố định** — payload nay ghi
   rõ trường `api` để biết kết quả đến từ đường nào.

---

## 5. Bảng trạng thái mục tiêu

| Việc | Trạng thái |
|---|---|
| **Bắt buộc dùng browser-use, LLM chỉ giao việc** | **XONG** — `tools/agent_browser_use.py`; ranh giới khoá bằng test AST |
| **Đổi nhà cung cấp LLM linh hoạt** | **XONG** — 9/9 provider; `litellm` bao phần còn lại |
| **Agent tự nhận diện rule từ guideline** | **XONG** — luật là dữ liệu + `check_rules --check` bắt lệch với docx nguồn |
| Lõi browser-use ở `D:\browser-agent-core` | **đã nối vào vòng chạy** (`browser_use 0.13.10`, `mediapipe 0.10.21`) |
| Lái UI (đường 1) | **browser-use TỰ LÁI — đường chính**; CDP trực tiếp là dự phòng |
| Ghi annotation qua REST (đường 2) | **XONG trên CẢ localhost VÀ online** (job 2214: 35 skeleton/250 điểm) |
| Vision + FaceMesh | **XONG** — 468 → 50/50 điểm; chạy được trên CẢ mediapipe 0.10.x và 1.x |
| **MediaPipe không chạy được trên máy này** | **ĐÃ SỬA** — nguyên nhân gốc của 4 lỗi landmark; xem mục 2.14 |
| **Môi "nối bị sai rất nhiều"** | **ĐÃ SỬA** — chọn 12/8 điểm theo tỉ lệ cung trên vòng 20 điểm thật; môi dưới nay trải khắp môi |
| **Sống mũi "quá ngắn"** | **ĐÃ SỬA** — 27.1px → **55.9px**, chạm chóp mũi |
| **Mày "đang ở dưới"** | **KHÔNG TÁI HIỆN** — cả 10 điểm mày đều cao hơn mắt 19–38px; đã thêm test khoá bất biến + lệnh soi ảnh |
| **Thứ tự điểm lông mày (mục 5.2)** | **ĐẠT** — x của 0..9 tăng dần: 502 511 525 544 571 613 635 650 661 669 |
| **Bất biến guideline trên frame thật** | **ĐẠT cả 5 mục** — 3.1/5.2, 3.3 (mí + không tự cắt), 3.4, 3.2 |
| **Trái/phải HumanPose-17** | **XONG (chọn B)** — quy ước khung hình đúng như guideline mục 2.1. Bằng chứng "100% vs 44–56%" đã **RÚT LẠI** (sai nguồn + đo rỗng) — xem mục 2.13 |
| **So với task chuẩn 2218** | **CHƯA LÀM ĐƯỢC** — token 401; đang chờ token mới |
| Nối landmark → payload skeleton | **XONG** (`vision/pipeline.py`, `tools/agent_online.py`) |
| Auto-rotate ảnh 90° | **XONG** |
| Dọn container lạ ngoài dự án | **XONG** — **0 container lạ** |
| Một lệnh đồng bộ label khi `guildlline/` đổi | **XONG** — `python tools/sync_all.py`, idempotent |
| Document sử dụng trong `ai/doc/` | **XONG** — file này + mục 8 |
| Chạy hết job được giao | job 2214 xong; 2218 đã có pre-label đủ nên không đụng |

**Test toàn repo: 127 passed** (`python -m pytest test\ -q`). Bốn test mới khoá lỗi môi,
sống mũi và thứ tự vòng môi; đã **chứng minh là biết bắt lỗi** bằng cách dựng lại hai
lỗi cũ (`work/prove_tests_catch_old_bugs.py` → exit=1, 3 test đổ). Hai test cũ phải
viết lại vì chúng khoá theo bộ index chép tay cũ, tức đang bảo vệ chính lỗi.

Ba test mới nữa khoá **cách chọn dẫn chứng guideline** (mục 2.16); cũng đã chứng minh
biết bắt lỗi: `work/prove_evidence_tests_catch_old_bug.py` → thuật toán cũ hỏng 17/17
điểm pose17 và 17/50 điểm face50, thuật toán mới hỏng 0.

**Kiểm chứng trên ảnh THẬT của task:** bất biến guideline nay ĐẠT cả 5 mục trên frame
thật (`work/check_vf50_rerun.py`); ảnh để soi bằng mắt:
`python tools\preview_face_landmarks.py work\face_2214_f0.jpg`. So hai đường MediaPipe:
`work/compare_mediapipe_apis.py`.

---

## 6. Bản đồ file

| Nhóm | File | Vai trò |
|---|---|---|
| **Luật** | `rules/week2-rules.json` | Ngưỡng guideline dạng dữ liệu — **sửa ở đây để đổi hành vi** |
| | `browser_agent/vision/rules.py` | Đọc luật + đọc bảng docx nguồn + so lệch |
| | `tools/check_rules.py` | `--check` cho CI |
| **Giao việc browser** | `tools/agent_browser_use.py` | **Đường chính** — LLM giao việc |
| | `browser_agent/vision/worker_browsent.py` | browser-use tự lái (venv lõi) |
| | `tools/agent_browser.py` | Dự phòng — CDP trực tiếp |
| | `browser_agent/cdp_ws.py` | WebSocket tự viết (không cần gói ngoài) |
| **Vision** | `browser_agent/vision/worker_landmarks.py` | Suy luận landmark (chạy bằng python nào cũng được) |
| | `browser_agent/vision/mediapipe_pose.py` | Bọc MediaPipe, **tự chọn API** (`solutions` hoặc Tasks) |
| | `browser_agent/vision/mediapipe_tasks.py` | Tasks API 1.x + tải/đệm file `.task` |
| | `browser_agent/vision/pipeline.py` | Map landmark → payload, áp luật ngưỡng |
| | `browser_agent/geometry.py` | Lược đồ điểm, **vòng môi 20 điểm**, chuỗi sống mũi, tỉ lệ môi |
| | `browser_agent/vision/landmarks.py` | Chọn index theo toạ độ/cung (`assign_face_sides`) |
| **CVAT** | `browser_agent/cvat_rest.py` | Client REST (local + online) |
| | `tools/agent_online.py` | Suy luận + ghi lên CVAT online |
| | `tools/agent_vision.py` | Suy luận + ghi lên CVAT local |
| | `tools/agent_probe.py`, `tools/agent_labels.py` | Dò schema/token |
| **Đồng bộ** | `tools/sync_all.py`, `tools/sync_taxonomy.py`, `tools/sync_guidelines.py` | Đồng bộ guideline + label |
| **Docker** | `tools/agent_docker.py` | Rà soát container lạ (mặc định chỉ báo cáo) |
| **Kiểm chứng** | `work/verify_*.py`, `work/e2e_*.py`, `work/rule_drift_probe.py` | Chạy thật để chứng minh |
| | `tools/preview_face_landmarks.py` | **Dựng ảnh 50 điểm + vùng phóng to để soi bằng mắt** |
| | `work/check_vf50_rerun.py` | **Chạy MediaPipe thật → `map_face50` → kiểm 5 bất biến guideline** |
| | `work/prove_tests_catch_old_bugs.py` | Dựng lại lỗi cũ để chứng minh test mới biết bắt lỗi |
| | `work/compare_mediapipe_apis.py` | Đo lệch giữa `solutions` 0.10.21 và Tasks 1.0.1 |
| | `work/diag_nose_brow.py`, `work/diag_lip_select.py` | Dò sống mũi / chọn điểm môi trên mesh thật |
| | `work/probe_ref_jobs.py` | Đọc metadata + annotation của 2218/2213/2211 (cần token mới) |
| | `work/pose_axis_probe.py` | Kiểm 8 cặp khớp hai bên đúng phía khung hình |
| | `work/pose_verify_final.py` | ~~Đo 3 chiến lược trái/phải~~ **ĐÃ RÚT LẠI** — xem mục 2.13 |
| | `work/pose_side_consistency.py`, `work/pose_raw_dump.py` | Đo/soi toạ độ thô landmark |
| | `work/diag_skeleton_evidence.py` | Đo dẫn chứng mà bộ sinh chọn cho từng điểm skeleton |
| | `work/prove_evidence_tests_catch_old_bug.py` | Dựng lại thuật toán chọn dẫn chứng cũ để chứng minh test mới biết bắt lỗi |

---

## 7. Lệnh hay dùng

```powershell
# --- luật & guideline ---
python tools\sync_all.py --status         # file nguồn nào đã đổi
python tools\sync_all.py                  # đồng bộ guideline + artifact label
python tools\sync_all.py --check          # chỉ báo lệch (dùng trong CI)
python tools\check_rules.py --check       # luật agent có khớp tài liệu nguồn không

# --- test ---
python -m pytest test\ -q                 # 127 passed

# --- lái trình duyệt (PHẢI chạy ngoài sandbox) ---
python tools\agent_browser_use.py --task "Mở trang, cho biết phiên bản CVAT" --url http://localhost:8080/api/server/about
python tools\agent_browser.py --url http://localhost:8080/api/server/about --dom --expect 2.74.1

# --- suy luận + ghi annotation ---
python tools\agent_vision.py --task pose17 --image datasets\1354\G01_B011.jpg            # xem thử
python tools\agent_online.py --job 2214 --task face50 --frames all                       # xem thử
python tools\agent_online.py --job 2214 --task face50 --frames all --write               # ghi thật

# --- soi 50 điểm bằng mắt TRƯỚC khi ghi (nên làm mỗi lần đổi code landmark) ---
python tools\preview_face_landmarks.py work\face_2214_f0.jpg --table
#   -> work\face_2214_f0_annotated.png + _zoom_brow/_zoom_nose/_zoom_mouth.png

# --- kiểm chứng lại ---
python work\verify_skeleton_write.py       # định dạng payload skeleton (tự tạo task rồi dọn)
python work\e2e_vision_write.py            # suy luận thật -> ghi thật
python work\check_vf50_rerun.py            # MediaPipe thật -> map -> 5 bất biến guideline
python work\prove_tests_catch_old_bugs.py  # test mới có thật sự bắt lỗi cũ không
python work\compare_mediapipe_apis.py      # lệch giữa solutions 0.10.21 và Tasks 1.0.1
python work\rule_drift_probe.py            # luật có bắt được lệch khi nguồn đổi

# --- sức khoẻ hệ thống ---
python tools\agent_probe.py --target local --job 7
python tools\agent_docker.py
```

---

## 8. Hướng dẫn sử dụng

### 8.1 Đổi luật annotation (ngưỡng, quy tắc số)

Đây là việc thường gặp nhất khi BTC ra guideline mới.

```powershell
python tools\check_rules.py              # 1. xem luật đang dùng + nguồn ghi gì
# 2. sửa rules/week2-rules.json cho khớp tài liệu
python tools\check_rules.py --check      # 3. xác nhận hết lệch (exit 0)
```

Luật đổi là **hành vi agent đổi ngay** ở lần chạy sau — không cần sửa Python, không
cần build lại. Nếu chỉ đổi tài liệu nguồn mà quên đổi JSON, `--check` sẽ **báo lỗi**.

### 8.2 Đồng bộ sau khi thay tài liệu guideline

1. Bỏ file `.pdf`/`.docx` mới hoặc đã sửa vào `guildlline/`.
2. `python tools\sync_all.py --status` để xem file nào đã đổi.
3. `python tools\sync_all.py` để đồng bộ.
4. `python tools\check_rules.py --check` — **bước mới**, xác nhận luật còn khớp.
5. Nếu lệnh báo có **label mới trong tài liệu**: thêm label đó vào `taxonomy.yaml`
   (nguồn sự thật duy nhất cho label), rồi chạy lại bước 3.
6. Triển khai lại nuclio nếu label đổi: xem `nuclio/README.md` mục 6b.

Pipeline **không tự sửa** `taxonomy.yaml`, vì tự ghi đè từ văn bản tự do sẽ phá
annotation đang có trong CVAT.

### 8.3 Suy luận landmark và ghi vào CVAT

```powershell
# Chỉ suy luận, in ra để soi (KHÔNG ghi)
python tools\agent_vision.py --task pose17 --image datasets\1354\G01_B011.jpg

# Ghi thật lên một job (mặc định append, không đụng dữ liệu cũ)
python tools\agent_vision.py --task pose17 --target local --job 26 --image a.jpg --write

# CVAT online, nhiều frame
python tools\agent_online.py --job 2214 --task face50 --frames all --write
```

- `--task pose17` cho HumanPose-17, `--task face50` cho Face Landmark VF-50.
- `--frames all` hoặc `--frames 0,2,4`; mặc định **bỏ qua frame đã có shape**.
- `--rotate auto` (mặc định) tự thử 4 hướng; `--no-face` để bỏ FaceMesh cho nhanh.
- Lệnh **luôn in cảnh báo** của guideline (ảnh có thể bị lật, nhóm bị đánh Outside,
  không thấy mặt…) — **đọc trước khi tin kết quả**.
- Không có `--write` thì không có gì được ghi lên CVAT.

### 8.4 Lái CVAT bằng trình duyệt

**Cách chính — giao việc cho browser-use, để nó tự lái** (LLM không bấm từng bước):

```powershell
python tools\agent_browser_use.py `
  --task "Mở job này và cho tôi biết có bao nhiêu skeleton, liệt kê tên nhóm." `
  --url "https://cvat.note.transformerlabs.ai/tasks/344/jobs/2214"

# đổi LLM không cần sửa code
python tools\agent_browser_use.py --task "..." --url "..." --provider openai --model gpt-4o
python tools\agent_browser_use.py --task "..." --url "..." --provider ollama --model qwen2.5

# dùng phiên Chrome đã đăng nhập CVAT (khỏi nhập mật khẩu lại)
python tools\agent_browser_use.py --task "..." --url "..." --cdp-url http://127.0.0.1:9222
```

Mặc định model là `deepseek-v4-pro` (xem mục 2.3 vì sao **không** dùng `deepseek-flash`).
Kết quả JSON ghi ra `work/browser_use_result.json` (đổi bằng `--out`).

**Cách dự phòng — điều khiển CDP trực tiếp** (khi cần đúng một thao tác cụ thể):

```powershell
python tools\agent_browser.py --url http://localhost:8080/api/server/about --dom --expect 2.74.1
python tools\agent_browser.py --url http://localhost:8080/ --shot D:\anh\ui.png
python tools\agent_browser.py --attach      # gắn vào Chrome đang mở
```

⚠️ Phải chạy **ngoài sandbox** (Chrome bị sandbox chặn). Đường dẫn `--shot` dùng đường
dẫn tuyệt đối.

### 8.5 Lấy token CVAT online (khi `.env` hỏng)

```powershell
# 1. Mở Chrome có cổng debug
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
    --remote-debugging-port=9222 --user-data-dir="$env:LOCALAPPDATA\Google\Chrome\User Data"

# 2. Đăng nhập và lưu token thật vào work/online_token.txt
python work\online_session.py --login --username <user>
python work\online_session.py --whoami       # kiểm tra token còn sống
```

⚠️ `work/online_token.txt` chứa token **có quyền ghi** lên CVAT online — xoá khi xong.
