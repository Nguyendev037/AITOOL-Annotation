# HƯỚNG DẪN CHỌN MASK SAM CHO ANNOTATION SEMANTIC SEGMENTATION TRÊN CVAT

**AI20K • Data Annotation • BDD100K / Semantic Segmentation • Student Annotation Guideline**

Tài liệu này chuẩn hóa quy trình **chọn mask ứng viên (candidate mask) do SAM sinh ra** và gán nhãn semantic trên CVAT. Nội dung hợp nhất từ *Annotation Guideline (Bounding Box, Polygon & Polyline)* và *Hướng dẫn gán nhãn Semantic Segmentation*.

> **Thứ tự ưu tiên:** nếu guideline chính thức của batch/customer có quy định khác, **guideline của batch/customer được ưu tiên**. Tài liệu này chuẩn hóa rule set G01 cho bài thực hành.

---

## 1. Mục tiêu và phạm vi

- Tạo annotation 2D nhất quán, đúng taxonomy, đủ chất lượng để **review**, so sánh với ground truth và dùng cho pipeline huấn luyện/evaluation.
- Dữ liệu: ảnh giao thông định dạng **.jpg** trong thư mục `images` (semantic segmentation dùng `segmentation/images`).
- Công cụ: **CVAT**.
- **Học viên không được sử dụng annotation/ground truth có sẵn** trong quá trình làm bài.
- Chỉ annotate các class được liệt kê trong tài liệu này.
- **Không tự tạo class mới, không đổi tên class, không gộp class theo cảm tính.**

---

## 2. Nguyên tắc nền tảng của semantic segmentation

**Semantic segmentation là gán nhãn theo từng pixel, không phải theo instance.**

- Mỗi pixel được gán theo **class semantic**.
- Bài toán **không giữ identity riêng cho từng instance cùng class**. Hai chiếc xe cùng class `car` nằm cạnh nhau có thể nằm trong cùng một mask `car`; không bắt buộc tách thành hai đối tượng riêng.
- **Không bao giờ được để hai class chồng lấn** trên cùng một pixel (RULE 01).
- **Chỉ gán nhãn các pixel đang nhìn thấy.** Không suy đoán và tô phần vật thể bị che khuất.
- Màu RGB **chỉ dùng để visualize/overlay**. Quyết định annotation phải dựa trên **ngữ nghĩa class**, không dựa vào màu hiển thị.

### Ba rule bắt buộc

| Rule | Nội dung |
|---|---|
| **RULE 01 — KHÔNG CHỒNG LẤN** | Mỗi pixel thuộc tối đa một class semantic. Không được tạo hai mask/class chồng lên cùng một vùng ảnh. |
| **RULE 02 — BIÊN THEO BẰNG CHỨNG** | Biên mask phải bám theo biên **nhìn thấy** của vật thể/vùng trên ảnh. Không "vẽ ước lượng" ra ngoài phần có bằng chứng hình ảnh. |
| **RULE 03 — KHÔNG ÉP CLASS** | Nếu pixel/vùng không thể gán chắc chắn vào một trong 19 class, đánh dấu để review theo SOP của lớp; **không ép vào class gần giống chỉ để lấp kín ảnh**. |

---

## 3. Hai nhóm shape theo loại bài (BDD100K 2D)

| Nhóm nhãn | Shape trên CVAT | Class áp dụng |
|---|---|---|
| Object instance | Rectangle / Bounding Box | `pedestrian`, `rider`, `car`, `truck`, `bus`, `train`, `motorcycle`, `bicycle`, `traffic light`, `traffic sign` |
| Drivable area | Polygon | `area/drivable`, `area/alternative` |
| Lane marking | Polyline | `lane/crosswalk`, `lane/double white`, `lane/double yellow`, `lane/road curb`, `lane/single other`, `lane/single white`, `lane/single yellow` |

> **Quan trọng:** Không dùng Polygon và Polyline thay thế lẫn nhau trong cùng bài. Drivable area dùng **Polygon**; lane marking dùng **Polyline**. Điều này giúp annotation nhất quán và có thể evaluate.

**Liên hệ với mask semantic:** Khi làm bài semantic segmentation, mask/brush là công cụ chính cho vùng pixel phức tạp; có thể dùng Polygon cho vùng lớn có biên tương đối rõ nếu workflow của lớp cho phép. Tập class và color map ở Mục 4 là nguồn chuẩn cho việc gán nhãn pixel.

---

## 4. Danh sách class và color map (19 class)

| Class | Màu HEX | RGB |
|---|---|---|
| road | `#804080` | 128, 64, 128 |
| sidewalk | `#F423E8` | 244, 35, 232 |
| building | `#464646` | 70, 70, 70 |
| wall | `#66669C` | 102, 102, 156 |
| fence | `#BE9999` | 190, 153, 153 |
| pole | `#999999` | 153, 153, 153 |
| traffic_light | `#FAAA1E` | 250, 170, 30 |
| traffic_sign | `#DCDC00` | 220, 220, 0 |
| vegetation | `#6B8E23` | 107, 142, 35 |
| terrain | `#98FB98` | 152, 251, 152 |
| sky | `#4682B4` | 70, 130, 180 |
| person | `#DC143C` | 220, 20, 60 |
| rider | `#FF0000` | 255, 0, 0 |
| car | `#00008E` | 0, 0, 142 |
| truck | `#000046` | 0, 0, 70 |
| bus | `#003C64` | 0, 60, 100 |
| train | `#005064` | 0, 80, 100 |
| motorcycle | `#0000E6` | 0, 0, 230 |
| bicycle | `#770B20` | 119, 11, 32 |

**Lưu ý:**
- Đây là **palette hiển thị** của bài tập. Khi cấu hình CVAT, nên đặt màu label tương ứng để overlay nhất quán giữa các nhóm.
- **Tuyệt đối không** có class ngoài danh sách 19 class trên.

---

## 5. Quy trình chọn mask ứng viên SAM

### 5.1. Trình tự thao tác

1. Mở đúng **Job / đúng Organization**, kiểm tra **label set** trước khi bắt đầu.
2. **Xác định class semantic trước**, rồi mới chọn candidate mask. Không chọn mask trước rồi mới gán class theo hình dạng.
3. Ưu tiên annotate **vùng lớn trước** (`road`, `sky`, `building`, `vegetation`), sau đó tới **object nhỏ/mảnh** (`pole`, `traffic_light`, `traffic_sign`, chi tiết người, xe hai bánh).
4. Với mỗi vùng, xem xét toàn bộ candidate do SAM gợi ý và chọn candidate **bám sát biên nhìn thấy nhất**.
5. **Zoom** để kiểm tra và chỉnh boundary.
6. Thường xuyên **giảm opacity overlay** để nhìn rõ ảnh gốc.
7. Dùng **Lock / Hide / filter label** khi frame dày để tránh sửa nhầm.
8. **Save thường xuyên**, tự review toàn ảnh trước khi chuyển state completed.

### 5.2. Tiêu chí chấp nhận một candidate mask

Chọn candidate khi **tất cả** điều kiện sau đúng:

- Candidate bao phủ đúng vùng mang **một class semantic duy nhất** theo ngữ nghĩa, không lấn sang class khác.
- Biên candidate bám theo **đường biên nhìn thấy** giữa hai semantic region; không cắt vào trong object và không lấy thừa background đáng kể.
- Candidate **chỉ bao gồm các pixel đang nhìn thấy**; không bao gồm phần bị object khác che (occlusion) hay phần nằm ngoài frame (truncation).
- Candidate **không chồng lấn** với mask của class khác đã có.
- Candidate không tạo **lỗ trống giả** giữa các vùng kề nhau do thao tác cẩu thả.

### 5.3. Xử lý khi không có candidate đạt yêu cầu

- **Chỉnh sửa** candidate bằng Mask/Brush (và Polygon cho vùng lớn có biên tương đối rõ nếu workflow của lớp cho phép).
- Nếu vẫn **không đủ bằng chứng hình ảnh** để xác định class hoặc boundary: **không đoán** — tạo **Issue** theo Mục 8.
- Không cố đạt **100% coverage** bằng cách đoán. Với vùng không đủ bằng chứng, ưu tiên đưa review.

### 5.4. Nhiều instance cùng class

Vì semantic segmentation **không giữ identity**, một mask cùng class có thể bao trùm nhiều instance cùng class mà không cần tách rời. Điều kiện bắt buộc vẫn là: mọi pixel trong mask phải đúng class semantic đó và không chồng lấn class khác.

---

## 6. Quy tắc biên, che khuất và cắt mép

### 6.1. Biên và vùng kề nhau

| Tình huống | Quy tắc |
|---|---|
| **Biên class** | Đi theo đường biên **nhìn thấy** giữa hai semantic region. Zoom khi cần, đặc biệt với người, rider, xe hai bánh, pole, biển báo và đèn tín hiệu. |
| **Không chồng lấn** | Hai class khác nhau không được cùng chiếm một pixel. Nếu hai object chồng nhau theo phối cảnh, **pixel hiển thị thuộc object ở phía trước**. |
| **Không tạo lỗ giả** | Không để lỗ trống giữa các vùng kề nhau do thao tác mask/polygon cẩu thả. **Tuy nhiên không được "lấp" vùng chưa rõ bằng class đoán.** |
| **Object mảnh** | Pole, traffic sign/light support, bicycle/motorcycle và chi tiết người cần **giữ hình dạng hợp lý**; tránh làm mask phình quá mức. |
| **Object nhỏ/xa** | Nếu vẫn nhận dạng được class thì annotate. Nếu quá nhỏ/mờ để xác định chắc chắn, **đưa review thay vì đoán**. |

### 6.2. Occlusion và truncation

| Thuộc tính / tình huống | Quy tắc | Ví dụ |
|---|---|---|
| **OCCLUSION** | Semantic segmentation **chỉ gán các pixel đang nhìn thấy**. Không suy đoán và tô phần vật thể bị che bởi vật khác. | Xe phía sau xe tải; người bị xe che một phần. |
| **TRUNCATION** | **Chỉ annotate phần nằm trong ảnh.** Mask dừng tại biên ảnh; không cần suy đoán phần ở ngoài frame. | Xe chỉ xuất hiện một phần ở mép trái/phải ảnh. |
| **Cả hai** | Vừa bị che vừa bị cắt bởi biên ảnh → chỉ tô phần nhìn thấy, dừng ở biên ảnh. | Xe ở mép ảnh và đồng thời bị object khác che. |
| **Reflection / shadow** | **Không gán** reflection, bóng đổ hoặc hình ảnh trên billboard/màn hình thành object thật, trừ khi guideline riêng của batch quy định khác. | — |
| **Attribute (nhánh BBox)** | Với object bị che/cắt mép, vẫn annotate nếu còn đủ bằng chứng thị giác để xác định class; dùng attribute phù hợp: `occluded=true` khi bị object khác che; `truncated=true` khi bị cắt bởi biên ảnh. | — |

> **Không chắc?** Không tự suy luận class hoặc boundary. Tạo **Issue/comment** và đưa Reviewer xử lý.

---

## 7. Các cặp class dễ nhầm

| Cặp dễ nhầm | Quy tắc thực hành |
|---|---|
| `road` vs `sidewalk` | `road` = phần mặt đường dành cho phương tiện; `sidewalk` = lối đi bộ/viền hè tách khỏi mặt đường. |
| `building` vs `wall` | `building` = bề mặt thuộc công trình/tòa nhà; `wall` = tường độc lập hoặc tường ranh giới, không được xem là mặt chính của tòa nhà. |
| `wall` vs `fence` | `wall` thường là bề mặt kín/đặc; `fence` là hàng rào có cấu trúc thanh/lưới hoặc ranh giới dạng fence. |
| `vegetation` vs `terrain` | `vegetation` = cây/bụi/lá; `terrain` = đất/cỏ/bề mặt tự nhiên thấp, không được xem là vegetation dạng cây/bụi. |
| `person` vs `rider` | `rider` = người đang cưỡi/điều khiển xe hai bánh hoặc phương tiện tương ứng; `person` = người đi bộ/đứng/ngồi không thuộc rider. Rider được annotate riêng ở pixel người, phương tiện giữ class riêng. |
| `car` vs `truck` vs `bus` | Chọn theo loại phương tiện thực tế. Nếu hình quá xa/mờ để phân biệt đáng tin cậy, **escalate thay vì đoán**. |
| `motorcycle` vs `bicycle` | Phân biệt phương tiện **có động cơ** với xe đạp. |

---

## 8. Vùng không chắc chắn và escalation

Khi gặp case chưa chắc chắn, **ưu tiên quy trình review** thay vì "đoán cho xong".

### 8.1. Format Issue

| Issue type | Ví dụ |
|---|---|
| `UNCERTAIN_CLASS` | car vs truck |
| `UNCERTAIN_BOUNDARY` | không rõ extent do occlusion |
| `UNCERTAIN_SCOPE` | không chắc object có thuộc phạm vi bài |
| `ATTRIBUTE_CHECK` | không chắc `occluded` / `truncated` |
| `UNCERTAIN_SMALL_OBJECT` | object quá nhỏ/mờ để xác định class chắc chắn |

### 8.2. Quy tắc escalation

- Không cố gắng đạt 100% coverage bằng cách đoán. Với vùng không đủ bằng chứng hình ảnh, **ưu tiên đưa review**.
- Nếu SOP có label/flag **ignore** hoặc **unlabeled**, chỉ sử dụng đúng theo cấu hình của batch. **Không tự tạo ignore class.**
- Issue nên nêu **ngắn gọn loại vấn đề** bằng các mã ở trên.
- Case **lặp lại nhiều lần** phải được **mentor/lead chốt thành decision log** để mọi nhóm áp dụng giống nhau.
- **Không tự đặt quy tắc mới, không tự invent rule.**

### 8.3. Nguyên tắc cuối cùng

> Nếu hình ảnh không cung cấp đủ bằng chứng hoặc guideline không trả lời được case đó: **dừng suy đoán, tạo Issue và escalate.**

---

## 9. Checklist chất lượng trước khi Submit

☐ Đúng class và đúng loại shape theo bảng taxonomy.
☐ Không bỏ sót object rõ ràng thuộc scope.
☐ Không có annotation trùng lặp cùng một object.
☐ Không có vùng mask chồng lấn giữa các class.
☐ Không có lỗ trống do thao tác ở các vùng lẽ ra đã xác định rõ class.
☐ Bounding box đủ sát, không chứa quá nhiều nền và không vượt biên ảnh.
☐ Polygon/polyline bám đúng biên/đường quan sát được, không tự cắt hoặc nhảy qua vùng không có evidence.
☐ Boundary của `road`/`sidewalk`/`building`/`sky`/`vegetation` bám đúng ảnh.
☐ `person`/`rider`/`car`/`bicycle`/`motorcycle` và object nhỏ được kiểm tra ở mức zoom phù hợp.
☐ Không tô phần object bị che khuất hoặc nằm ngoài ảnh.
☐ Không nhầm `person` với `rider`; vehicle class được kiểm tra lại.
☐ Attributes `occluded`/`truncated` đã được gán đúng khi cần.
☐ Không có class tự tạo, class bị đổi tên hoặc class ngoài danh sách 19 class.
☐ Color map/label name hiển thị đúng cấu hình.
☐ Mọi case không chắc đã có Issue/comment để reviewer xử lý.
☐ Các Issue còn mở đã được xử lý hoặc chuyển reviewer.
☐ Review ít nhất **10 ảnh ngẫu nhiên** của batch trước khi submit cuối.
☐ Đã Save và tự review toàn bộ job trước khi chuyển sang Validation.

---

## 10. Tiêu chí Reviewer kiểm tra và đánh giá

| Hạng mục | Reviewer kiểm tra |
|---|---|
| **Taxonomy** | Đúng class, không class ngoài scope |
| **Completeness** | Không thiếu object/area/lane rõ ràng |
| **Geometry** | BBox sát; polygon/polyline đúng hình học |
| **Attributes** | `occluded`/`truncated` đúng quy tắc |
| **Consistency** | Các case tương tự được annotate theo cùng một quy tắc |
| **Escalation** | Case chưa có rule được đưa mentor/lead chốt, không tự invent rule |

### Tiêu chí đánh giá semantic

- **Độ chính xác semantic:** pixel được gán đúng class theo guideline.
- **Độ chính xác boundary:** không cắt vào object và không lấy thừa background đáng kể.
- **Consistency:** cùng loại tình huống phải được xử lý giống nhau giữa các ảnh và giữa các annotator.
- **Metric định lượng** khi có Ground Truth: **per-class IoU** và **mean IoU (mIoU)**. Ngưỡng pass do chương trình/mentor quy định cho từng batch.

---

## 11. Quick reference

| Nếu gặp tình huống… | Hành động | Không làm | Cần review? |
|---|---|---|---|
| Xe/người rõ ràng | BBox sát object (nhánh BBox) / mask đúng class (nhánh semantic) | Gộp nhiều object | Không |
| Bị che một phần | BBox + `occluded=true`; với mask: **chỉ tô pixel nhìn thấy**, không suy đoán phần bị che | Bỏ object chỉ vì bị che / tô phần bị che | Không, nếu class rõ |
| Bị cắt mép ảnh | BBox + `truncated=true`; mask tô tới biên ảnh và dừng | Vẽ box vượt ra ngoài ảnh / suy đoán phần ngoài frame | Không, nếu class rõ |
| Drivable area | Polygon bám biên quan sát được | Dùng Polyline tùy ý | Nếu boundary không rõ |
| Lane marking | Polyline theo tim/biên vạch | Dùng Polygon thay thế | Nếu class/style không rõ |
| Hai class chồng mask | Sửa để mỗi pixel chỉ thuộc một class | Để tồn tại vùng chồng lấn | Không |
| Class không chắc | Tạo Issue | Đoán class | **Có** |
| Object quá nhỏ/mờ | Đưa review nếu không chắc | Tự suy đoán | **Có** |
| Vùng lớn có biên rõ | Mask/Brush hoặc Polygon theo workflow được chốt | Vẽ ước lượng ra ngoài evidence | Không |
| Reflection/shadow | Bỏ qua, không annotate như object thật | Tô thành object thật | Chỉ khi guideline batch nói khác |

---

## 12. Yêu cầu đầu ra (Output requirements)

1. **Mọi pixel được gán thuộc tối đa một class semantic** trong danh sách 19 class — không tồn tại vùng chồng lấn giữa các class.
2. **Không có lỗ trống giả** tại các vùng đã xác định rõ class; nhưng cũng **không lấp vùng chưa rõ bằng class đoán**.
3. **Mask chỉ chứa pixel nhìn thấy**, dừng tại biên ảnh; không suy đoán phần bị che hoặc nằm ngoài frame.
4. **Class name và color map đúng cấu hình** theo bảng ở Mục 4; không có class tự tạo, class đổi tên hoặc class ngoài danh sách.
5. **Mọi case không chắc chắn đều có Issue** kèm mã loại vấn đề (`UNCERTAIN_CLASS`, `UNCERTAIN_BOUNDARY`, `UNCERTAIN_SCOPE`, `ATTRIBUTE_CHECK`, `UNCERTAIN_SMALL_OBJECT`) để reviewer xử lý.
6. **Đã Save**, tự review toàn bộ job, review ít nhất **10 ảnh ngẫu nhiên** của batch trước khi submit cuối.
7. Khi có Ground Truth, kết quả được đánh giá bằng **per-class IoU và mIoU** theo ngưỡng pass do chương trình/mentor quy định cho từng batch.
8. Mọi case lặp lại nhiều lần phải được **mentor/lead chốt thành decision log** và áp dụng thống nhất trong toàn nhóm.
