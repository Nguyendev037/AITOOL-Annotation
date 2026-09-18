# HƯỚNG DẪN ANNOTATION — BOUNDING BOX, POLYGON & POLYLINE

**AI20K • Data Annotation • BDD100K 2D • Student Annotation Guideline**

Tài liệu này chuẩn hóa rule set **G01** cho bài thực hành annotation 2D trên **CVAT**. Nội dung được trích từ PDF gốc `guildlline/Annotation_Guideline_BBox_Polygon_Polyline.pdf`.

> **Thứ tự ưu tiên:** nếu guideline chính thức của batch/customer có quy định khác, **guideline của batch/customer được ưu tiên**.

---

## 1. Phạm vi và dữ liệu sử dụng

- Thư mục ảnh: `images`
- Định dạng ảnh: `.jpg`
- Học viên **không sử dụng annotation/ground truth có sẵn** trong quá trình làm bài.
- Chỉ annotate các class được liệt kê trong tài liệu này.
- **Không tự tạo class mới, không đổi tên class và không gộp class theo cảm tính.**

Mục tiêu: tạo annotation 2D nhất quán, đúng taxonomy, đủ chất lượng để review, so sánh với ground truth và dùng cho pipeline huấn luyện/evaluation.

Nguyên tắc: **không đoán**; không tự tạo class; case không rõ phải đưa review.

---

## 2. Taxonomy và loại shape bắt buộc

| Nhóm nhãn | CVAT shape | Class áp dụng |
|---|---|---|
| Object instance | Rectangle / Bounding Box | `pedestrian`, `rider`, `car`, `truck`, `bus`, `train`, `motorcycle`, `bicycle`, `traffic light`, `traffic sign` |
| Drivable area | Polygon | `area/drivable`, `area/alternative` |
| Lane marking | Polyline | `lane/crosswalk`, `lane/double white`, `lane/double yellow`, `lane/road curb`, `lane/single other`, `lane/single white`, `lane/single yellow` |

> **Quan trọng:** Không dùng Polygon và Polyline thay thế lẫn nhau trong cùng bài. Drivable area dùng **Polygon**; lane marking dùng **Polyline**. Điều này giúp annotation nhất quán và có thể chấm/evaluate được.

---

## 3. Quy tắc Bounding Box

- Vẽ box **bao sát** phần đối tượng cần annotate, hạn chế tối đa phần nền thừa.
- **Mỗi object = một annotation riêng.** Không dùng một box để bao nhiều object độc lập.
- Box **không được vượt ra ngoài biên ảnh**.
- Không bỏ sót object rõ ràng chỉ vì kích thước nhỏ hoặc ở xa. Nếu quá nhỏ/mờ để xác định class chắc chắn, **đưa review thay vì đoán**.
- **Không annotate** reflection, hình in trên billboard/màn hình, bóng đổ hoặc vật thể ngoài danh sách class, trừ khi guideline của batch yêu cầu.
- Với object bị che/cắt mép, **vẫn annotate nếu còn đủ bằng chứng thị giác** để xác định class; dùng attribute phù hợp.

### 3.1. Occluded và Truncated

| Attribute | Khi nào bật | Ví dụ |
|---|---|---|
| `occluded = true` | Object vẫn nằm trong scene nhưng một phần bị object khác che. | Xe phía sau xe tải; người bị xe che một phần. |
| `truncated = true` | Object bị cắt bởi biên ảnh, phần còn lại nằm ngoài frame. | Xe chỉ xuất hiện một phần ở mép trái/phải ảnh. |
| cả hai `= true` | Object vừa bị che vừa bị cắt bởi biên ảnh. | Xe ở mép ảnh và đồng thời bị object khác che. |

> **Không chắc?** Không tự suy luận class hoặc boundary. Tạo Issue/comment và đưa Reviewer xử lý.

---

## 4. Quy tắc Polygon và Polyline

### 4.1. Polygon — Drivable Area

- Bám sát biên vùng có thể quan sát được trên ảnh; không vẽ rộng theo suy đoán.
- Không để polygon tự cắt (self-intersection).
- Hạn chế điểm thừa trên đoạn thẳng; tăng mật độ điểm ở đoạn cong/phức tạp.
- Không tạo vùng overlap vô nghĩa. Nếu hai vùng có quan hệ hoặc ưu tiên đặc biệt, làm theo guideline của batch.
- Phân biệt `area/drivable` và `area/alternative` theo định nghĩa đã được giảng viên/mentor chốt cho batch; **không tự đổi nhãn khi chưa chắc**.

### 4.2. Polyline — Lane Marking

- Polyline phải đi theo đúng tim/biên lane marking theo quy ước của bài, không nối tắt qua vùng không có vạch.
- Giữ hướng vẽ nhất quán trong cùng dataset nếu batch có yêu cầu về direction.
- Kết thúc polyline tại điểm lane marking không còn đủ bằng chứng thị giác.
- Không dùng Polygon để thay cho lane marking chỉ vì vùng vạch có bề rộng.
- **Không tự thêm class lane mới** ngoài danh sách cho phép.

---

## 5. Quy tắc khi class hoặc boundary không rõ

Khi gặp case chưa chắc chắn, **ưu tiên quy trình review** thay vì "đoán cho xong". Có thể dùng format issue sau:

| Issue type | Ví dụ |
|---|---|
| `UNCERTAIN_CLASS` | car vs truck |
| `UNCERTAIN_BOUNDARY` | không rõ extent do occlusion |
| `UNCERTAIN_SCOPE` | không chắc object có thuộc phạm vi bài |
| `ATTRIBUTE_CHECK` | không chắc occluded / truncated |

---

## 6. Checklist chất lượng trước khi Submit

- Đúng class và đúng loại shape theo bảng taxonomy.
- Không bỏ sót object rõ ràng thuộc scope.
- Không có annotation trùng lặp cùng một object.
- Bounding box đủ sát, không chứa quá nhiều nền và không vượt biên ảnh.
- Polygon/polyline bám đúng biên/đường quan sát được, không tự cắt hoặc nhảy qua vùng không có evidence.
- Attributes `occluded`/`truncated` đã được gán đúng khi cần.
- Không có class tự tạo hoặc class bị đổi tên.
- Mọi case không chắc đã có Issue/comment để reviewer xử lý.
- Đã Save và tự review toàn bộ job trước khi chuyển sang Validation.

---

## 7. Tiêu chí Reviewer kiểm tra

| Hạng mục | Reviewer kiểm tra |
|---|---|
| **Taxonomy** | Đúng class, không class ngoài scope |
| **Completeness** | Không thiếu object/area/lane rõ ràng |
| **Geometry** | BBox sát; polygon/polyline đúng hình học |
| **Attributes** | Occluded/truncated đúng quy tắc |
| **Consistency** | Các case tương tự được annotate theo cùng một quy tắc |
| **Escalation** | Case chưa có rule được đưa mentor/lead chốt, không tự invent rule |

---

## 8. Quick Reference

| Tình huống | Làm gì | Không làm | Cần review? |
|---|---|---|---|
| Xe/người rõ ràng | BBox sát object | Gộp nhiều object | Không |
| Bị che một phần | BBox + `occluded=true` | Bỏ object chỉ vì bị che | Không, nếu class rõ |
| Bị cắt mép ảnh | BBox + `truncated=true` | Vẽ box vượt ra ngoài ảnh | Không, nếu class rõ |
| Drivable area | Polygon bám biên quan sát được | Dùng Polyline tùy ý | Nếu boundary không rõ |
| Lane marking | Polyline theo tim/biên vạch | Dùng Polygon thay thế | Nếu class/style không rõ |
| Class không chắc | Tạo Issue | Đoán class | **Có** |
| Object quá nhỏ/mờ | Đưa review nếu không chắc | Tự suy đoán | **Có** |

**Nguyên tắc cuối cùng:** Nếu hình ảnh không cung cấp đủ bằng chứng hoặc guideline không trả lời được case đó — **dừng suy đoán, tạo Issue và escalate.**
