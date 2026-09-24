<!-- GENERATED FILE - do not edit by hand.
     Produced by `python tools/sync_all.py` from the original documents in
     `guildlline/`. Edit the source documents and re-run the command; this
     file is overwritten. -->

# Guideline tổng hợp (sinh tự động)

Engine trích xuất PDF: `pdfplumber` (thứ tự ưu tiên: pypdf, pdfplumber, pypdfium2, pdfminer).

Nguồn gốc:

- `guildlline/Annotation_Guideline_BBox_Polygon_Polyline.pdf` (sha256 `63bce09da0e8`, 167723 bytes)
- `guildlline/Semantic_Segmentation_Annotation_Guideline.pdf` (sha256 `8d8d1dc910b2`, 203043 bytes)
- `guildlline/Week2_Guideline_Face_Landmark_VF50_HocVien_v1.3.docx` (sha256 `ac1e0e342e2d`, 3849351 bytes)
- `guildlline/Week2_Guideline_HumanPose17_HocVien_v1.1.docx` (sha256 `98b33f2abf58`, 2648357 bytes)


---

## Nguồn: `Annotation_Guideline_BBox_Polygon_Polyline.pdf`

<!-- page 1 -->

AI20K • Data Annotation • BDD100K 2D Guideline
ANNOTATION GUIDELINE
Bounding Box, Polygon & Polyline
Hướng dẫn thực hành cho học viên trên CVAT
Mục tiêu Tạo annotation 2D nhất quán, đúng taxonomy và đủ chất lượng để có thể review, so sánh với ground truth và sử
dụng cho pipeline huấn luyện/evaluation.
Dữ liệu ảnh giao thông
Công cụ CVAT
Bounding box cho object instance; polygon cho drivable area;
Phạm vi
polyline cho lane marking
Không đoán; không tự tạo class; case không rõ phải đưa
Nguyên tắc
review
Tài liệu này chuẩn hóa rule set G01 cho bài thực hành. Nếu guideline chính thức của batch/customer có quy định khác, guideline của
batch/customer được ưu tiên.
Tài liệu thực hành • Phiên bản 1.0

<!-- page 2 -->

AI20K • Data Annotation • BDD100K 2D Guideline
1. Phạm vi và dữ liệu sử dụng
● Thư mục ảnh: images
● Định dạng ảnh: .jpg
● Học viên không sử dụng annotation/ground truth có sẵn trong quá trình làm bài.
● Chỉ annotate các class được liệt kê trong tài liệu này.
● Không tự tạo class mới, không đổi tên class và không gộp class theo cảm tính.
2. Taxonomy và loại shape bắt buộc
Nhóm nhãn CVAT shape Class áp dụng
pedestrian, rider, car, truck, bus, train,
Object instance Rectangle / Bounding Box motorcycle, bicycle, traffic light, traffic
sign
Drivable area Polygon area/drivable, area/alternative
lane/crosswalk, lane/double white,
lane/double yellow, lane/road curb,
Lane marking Polyline
lane/single other, lane/single white,
lane/single yellow
Quan trọng Không dùng Polygon và Polyline thay thế lẫn nhau trong cùng bài. Drivable area dùng Polygon; lane marking dùng
Polyline. Điều này giúp annotation nhất quán và có thể chấm/evaluate được.
3. Quy tắc Bounding Box
● Vẽ box bao sát phần đối tượng cần annotate, hạn chế tối đa phần nền thừa.
● Mỗi object = một annotation riêng. Không dùng một box để bao nhiều object độc lập.
● Box không được vượt ra ngoài biên ảnh.
● Không bỏ sót object rõ ràng chỉ vì kích thước nhỏ hoặc ở xa. Nếu quá nhỏ/mờ để xác định class chắc chắn, đưa
review thay vì đoán.
● Không annotate reflection, hình in trên billboard/màn hình, bóng đổ hoặc vật thể ngoài danh sách class, trừ khi
guideline của batch yêu cầu.
● Với object bị che/cắt mép, vẫn annotate nếu còn đủ bằng chứng thị giác để xác định class; dùng attribute phù
hợp.
3.1. Occluded và Truncated
Attribute Khi nào bật Ví dụ
Object vẫn nằm trong scene nhưng một Xe phía sau xe tải; người bị xe che một
occluded = true
phần bị object khác che. phần.
Object bị cắt bởi biên ảnh, phần còn lại Xe chỉ xuất hiện một phần ở mép
truncated = true
nằm ngoài frame. trái/phải ảnh.
Object vừa bị che vừa bị cắt bởi biên Xe ở mép ảnh và đồng thời bị object
cả hai = true
ảnh. khác che.
Không chắc? Không tự suy luận class hoặc boundary. Tạo Issue/comment và đưa Reviewer xử lý.
Tài liệu thực hành • Phiên bản 1.0

<!-- page 3 -->

AI20K • Data Annotation • BDD100K 2D Guideline
4. Quy tắc Polygon và Polyline
4.1. Polygon – Drivable Area
● Bám sát biên vùng có thể quan sát được trên ảnh; không vẽ rộng theo suy đoán.
● Không để polygon tự cắt (self-intersection).
● Hạn chế điểm thừa trên đoạn thẳng; tăng mật độ điểm ở đoạn cong/phức tạp.
● Không tạo vùng overlap vô nghĩa. Nếu hai vùng có quan hệ hoặc ưu tiên đặc biệt, làm theo guideline của batch.
● Phân biệt area/drivable và area/alternative theo định nghĩa đã được giảng viên/mentor chốt cho batch; không tự
đổi nhãn khi chưa chắc.
4.2. Polyline – Lane Marking
● Polyline phải đi theo đúng tim/biên lane marking theo quy ước của bài, không nối tắt qua vùng không có vạch.
● Giữ hướng vẽ nhất quán trong cùng dataset nếu batch có yêu cầu về direction.
● Kết thúc polyline tại điểm lane marking không còn đủ bằng chứng thị giác.
● Không dùng Polygon để thay cho lane marking chỉ vì vùng vạch có bề rộng.
● Không tự thêm class lane mới ngoài danh sách cho phép.
5. Quy tắc khi class hoặc boundary không rõ
Khi gặp case chưa chắc chắn, ưu tiên quy trình review thay vì “đoán cho xong”. Có thể dùng format issue sau:
Issue type Ví dụ
UNCERTAIN_CLASS car vs truck
UNCERTAIN_BOUNDARY không rõ extent do occlusion
UNCERTAIN_SCOPE không chắc object có thuộc phạm vi bài
ATTRIBUTE_CHECK không chắc occluded / truncated
6. Checklist chất lượng trước khi Submit
☐ Đúng class và đúng loại shape theo bảng taxonomy.
☐ Không bỏ sót object rõ ràng thuộc scope.
☐ Không có annotation trùng lặp cùng một object.
☐ Bounding box đủ sát, không chứa quá nhiều nền và không vượt biên ảnh.
☐ Polygon/polyline bám đúng biên/đường quan sát được, không tự cắt hoặc nhảy qua vùng không có evidence.
☐ Attributes occluded/truncated đã được gán đúng khi cần.
☐ Không có class tự tạo hoặc class bị đổi tên.
☐ Mọi case không chắc đã có Issue/comment để reviewer xử lý.
☐ Đã Save và tự review toàn bộ job trước khi chuyển sang Validation.
7. Tiêu chí Reviewer kiểm tra
Hạng mục Reviewer kiểm tra
Taxonomy Đúng class, không class ngoài scope
Completeness Không thiếu object/area/lane rõ ràng
Geometry BBox sát; polygon/polyline đúng hình học
Attributes Occluded/truncated đúng quy tắc
Tài liệu thực hành • Phiên bản 1.0

<!-- page 4 -->

AI20K • Data Annotation • BDD100K 2D Guideline
Consistency Các case tương tự được annotate theo cùng một quy tắc
Case chưa có rule được đưa mentor/lead chốt, không tự
Escalation
invent rule
8. Quick Reference
Tình huống Làm gì Không làm Cần review?
Xe/người rõ ràng BBox sát object Gộp nhiều object Không
Bị che một phần BBox + occluded=true Bỏ object chỉ vì bị che Không, nếu class rõ
Bị cắt mép ảnh BBox + truncated=true Vẽ box vượt ra ngoài ảnh Không, nếu class rõ
Drivable area Polygon Polyline tùy ý Nếu boundary không rõ
Lane marking Polyline Polygon thay thế Nếu class/style không rõ
Class không chắc Tạo Issue Đoán class Có
Object quá nhỏ/mờ Đưa review nếu không chắc Tự suy đoán Có
Nguyên tắc cuối cùng Nếu hình ảnh không cung cấp đủ bằng chứng hoặc guideline không trả lời được case đó: dừng suy
đoán, tạo Issue và escalate.
Tài liệu thực hành • Phiên bản 1.0

---

## Nguồn: `Semantic_Segmentation_Annotation_Guideline.pdf`

<!-- page 1 -->

HƯỚNG DẪN GÁN NHÃN
SEMANTIC SEGMENTATION
Student Annotation Guideline • CVAT
Mục tiêu: gán đúng class cho từng pixel trong ảnh giao thông, với biên semantic nhất quán, không chồng lấn và có quy
trình rõ ràng cho vùng không chắc chắn.
1. Phạm vi và nguyên tắc chung
● Dữ liệu: ảnh .jpg trong thư mục segmentation/images. Học viên không sử dụng annotation/ground truth có sẵn trong
khi thực hành.
● Bài toán là semantic segmentation: mỗi pixel được gán theo class semantic, không giữ identity riêng cho từng instance
cùng class.
● Chỉ sử dụng 19 class đã quy định trong tài liệu này. Không tự tạo class, không đổi tên class, không ghép class theo
cảm tính.
● Màu RGB chỉ dùng để visualize/overlay. Quyết định annotation phải dựa trên ngữ nghĩa class, không dựa vào màu
hiển thị.
RULE 01 Mỗi pixel thuộc tối đa một class semantic. Không được tạo hai mask/class chồng lên cùng
một vùng ảnh.
RULE 02 Biên mask phải bám theo biên nhìn thấy của vật thể/vùng trên ảnh. Không “vẽ ước lượng” ra
ngoài phần có bằng chứng hình ảnh.
RULE 03 Nếu pixel/vùng không thể gán chắc chắn vào một trong 19 class, đánh dấu để review theo
SOP của lớp; không ép vào class gần giống chỉ để lấp kín ảnh.
2. Danh sách class và color map
Class Màu HEX RGB
road #804080 128, 64, 128
sidewalk #F423E8 244, 35, 232
building #464646 70, 70, 70
wall #66669C 102, 102, 156
fence #BE9999 190, 153, 153
pole #999999 153, 153, 153
traffic_light #FAAA1E 250, 170, 30
traffic_sign #DCDC00 220, 220, 0
vegetation #6B8E23 107, 142, 35
terrain #98FB98 152, 251, 152
sky #4682B4 70, 130, 180
person #DC143C 220, 20, 60
rider #FF0000 255, 0, 0
car #00008E 0, 0, 142
truck #000046 0, 0, 70
AI20K • Semantic Segmentation • Student Guideline

<!-- page 2 -->

Class Màu HEX RGB
bus #003C64 0, 60, 100
train #005064 0, 80, 100
motorcycle #0000E6 0, 0, 230
bicycle #770B20 119, 11, 32
Lưu ý: bảng trên là palette hiển thị của bài tập. Khi cấu hình CVAT, nên đặt màu label tương ứng để overlay nhất quán giữa
các nhóm.
3. Quy tắc vẽ mask và xử lý biên
BIÊN CLASS Đi theo đường biên nhìn thấy giữa hai semantic region. Zoom khi cần, đặc biệt với người,
rider, xe hai bánh, pole, biển báo và đèn tín hiệu.
KHÔNG CHỒNG LẤN Hai class khác nhau không được cùng chiếm một pixel. Nếu hai object chồng nhau theo phối
cảnh, pixel hiển thị thuộc object ở phía trước.
KHÔNG TẠO LỖ GIẢ Không để lỗ trống giữa các vùng kề nhau do thao tác mask/polygon cẩu thả. Tuy nhiên
không được “lấp” vùng chưa rõ bằng class đoán.
OBJECT MẢNH Pole, traffic sign/light support, bicycle/motorcycle và chi tiết người cần giữ hình dạng hợp lý;
tránh làm mask phình quá mức.
OBJECT NHỎ/XA Nếu vẫn nhận dạng được class thì annotate. Nếu quá nhỏ/mờ để xác định chắc chắn, đưa
review thay vì đoán.
OCCLUSION Semantic segmentation chỉ gán các pixel đang nhìn thấy. Không suy đoán và tô phần vật thể
bị che bởi vật khác.
TRUNCATION Chỉ annotate phần nằm trong ảnh. Mask dừng tại biên ảnh; không cần suy đoán phần ở
ngoài frame.
REFLECTION/SHADO Không gán reflection, bóng đổ hoặc hình ảnh trên billboard/màn hình thành object thật trừ
W khi guideline riêng của batch quy định khác.
4. Các cặp class dễ nhầm
Cặp dễ nhầm Quy tắc thực hành
road vs sidewalk road = phần mặt đường dành cho phương tiện; sidewalk =
lối đi bộ/viền hè tách khỏi mặt đường.
building vs wall building = bề mặt thuộc công trình/tòa nhà; wall = tường
độc lập hoặc tường ranh giới không được xem là mặt
chính của tòa nhà.
AI20K • Semantic Segmentation • Student Guideline

<!-- page 3 -->

Cặp dễ nhầm Quy tắc thực hành
wall vs fence wall thường là bề mặt kín/đặc; fence là hàng rào có cấu
trúc thanh/lưới hoặc ranh giới dạng fence.
vegetation vs terrain vegetation = cây/bụi/lá; terrain = đất/cỏ/bề mặt tự nhiên
thấp không được xem là vegetation dạng cây/bụi.
person vs rider rider = người đang cưỡi/điều khiển xe hai bánh hoặc
phương tiện tương ứng; person = người đi bộ/đứng/ngồi
không thuộc rider.
car vs truck vs bus Chọn theo loại phương tiện thực tế. Nếu hình quá xa/mờ
để phân biệt đáng tin cậy, escalate thay vì đoán.
motorcycle vs bicycle Phân biệt phương tiện có động cơ với xe đạp; rider được
annotate riêng ở pixel người, phương tiện giữ class riêng.
5. Thao tác khuyến nghị trên CVAT
1 Mở đúng Job / đúng Organization và kiểm tra label set trước khi bắt đầu.
2 Dùng Mask/Brush cho vùng pixel phức tạp; có thể dùng Polygon cho vùng lớn có
biên tương đối rõ nếu workflow của lớp cho phép.
3 Ưu tiên annotate vùng lớn trước (road, sky, building, vegetation), sau đó tới object
nhỏ/mảnh.
4 Zoom để chỉnh boundary; thường xuyên giảm opacity overlay để nhìn rõ ảnh gốc.
5 Dùng Lock/Hide/filter label khi frame dày để tránh sửa nhầm.
6 Nếu không chắc class/boundary, tạo Issue hoặc đánh dấu theo SOP review; không
tự đặt quy tắc mới.
7 Save thường xuyên, tự review toàn ảnh trước khi chuyển state completed.
6. Vùng không chắc chắn và escalation
● Không cố gắng đạt 100% coverage bằng cách đoán. Với vùng không đủ bằng chứng hình ảnh, ưu tiên đưa review.
● Nếu SOP có label/flag ignore hoặc unlabeled, chỉ sử dụng đúng theo cấu hình của batch. Không tự tạo ignore class.
● Issue nên nêu ngắn gọn loại vấn đề, ví dụ: UNCERTAIN_CLASS, UNCERTAIN_BOUNDARY hoặc
UNCERTAIN_SMALL_OBJECT.
● Case lặp lại nhiều lần phải được mentor/lead chốt thành decision log để mọi nhóm áp dụng giống nhau.
7. Quality checklist trước khi nộp
✓ Checklist
☐ Không có vùng mask chồng lấn giữa các class.
☐ Không có lỗ trống do thao tác ở các vùng lẽ ra đã xác định rõ class.
☐ Boundary của road/sidewalk/building/sky/vegetation bám đúng ảnh.
AI20K • Semantic Segmentation • Student Guideline

<!-- page 4 -->

☐ Person/rider/car/bicycle/motorcycle và object nhỏ được kiểm tra ở mức zoom phù hợp.
☐ Không tô phần object bị che khuất hoặc nằm ngoài ảnh.
☐ Không nhầm person với rider; vehicle class được kiểm tra lại.
☐ Không có class ngoài danh sách 19 class.
☐ Color map/label name hiển thị đúng cấu hình.
☐ Các Issue còn mở đã được xử lý hoặc chuyển reviewer.
☐ Review ít nhất 10 ảnh ngẫu nhiên của batch trước khi submit cuối.
8. Tiêu chí đánh giá
● Độ chính xác semantic: pixel được gán đúng class theo guideline.
● Độ chính xác boundary: không cắt vào object và không lấy thừa background đáng kể.
● Consistency: cùng loại tình huống phải được xử lý giống nhau giữa các ảnh và giữa annotator.
● Metric định lượng có thể dùng khi có Ground Truth: per-class IoU và mean IoU (mIoU). Ngưỡng pass do chương
trình/mentor quy định cho từng batch.
9. Quick reference cho học viên
Nếu gặp tình huống… Hành động
Object bị vật khác che Chỉ tô pixel nhìn thấy; không suy đoán phần bị che.
Object bị cắt bởi biên ảnh Tô tới biên ảnh và dừng.
Không chắc class Không đoán; tạo Issue/đưa review.
Hai class chồng mask Sửa để mỗi pixel chỉ thuộc một class.
Vùng lớn có biên rõ Mask/Brush hoặc Polygon theo workflow được chốt.
Object nhỏ/mảnh Zoom và bám biên; nếu không đủ evidence thì review.
Reflection/shadow Không annotate như object thật, trừ khi guideline batch nói
khác.
AI20K • Semantic Segmentation • Student Guideline

---

## Nguồn: `Week2_Guideline_Face_Landmark_VF50_HocVien_v1.3.docx`

# Guideline gán nhãn — VF-50 Face Landmark

Dành cho học viên. Phiên bản 1.3, Week 2, áp dụng cho 10 nhóm G01–G10.

## 1. Thông tin bài

Đặt 50 điểm landmark lên khuôn mặt người lái, chia thành 7 skeleton.

| Phần | Số ảnh mỗi nhóm | Việc phải làm |
|---|---|---|
| Có pre-label | 50 | Sửa vị trí điểm có sẵn, đặt toàn bộ trạng thái |
| Không pre-label | 20 | Tự dựng schema, đặt cả 50 điểm từ đầu |
| Tổng | 70 |  |

Ảnh 1280 × 720, mỗi ảnh có đúng một khuôn mặt. Toàn bộ ảnh lấy từ một phiên quay liên tục. 50 ảnh có pre-label của mỗi nhóm nằm thành vài dãy frame liên tiếp, xem mục 6.9. 20 ảnh tự làm được rải đều trên cả phiên nên không liên tiếp nhau.

### 1.1. Ba điều cần biết trước khi bắt đầu

1. Sẽ không thấy khung chữ nhật quanh khuôn mặt, chỉ có 7 nhóm điểm.

Mở ảnh lên, bạn thấy hai lông mày, sống mũi, hai mắt, môi ngoài và môi trong. Không có khung bao quanh mặt. Bài này không dùng khung đó, nên đừng đi tìm và đừng báo thiếu.

2. Mọi điểm đang để là "nhìn thấy", kể cả những điểm thật ra đang bị che.

Máy đặt sẵn cả 50 điểm ở trạng thái Visible cho mọi ảnh. Nói cách khác, phần trạng thái coi như chưa ai làm. Bạn phải xem từng điểm rồi tự chọn Visible, Occluded hay Outside — tính ra 2.500 điểm cho 50 ảnh của nhóm.

Đây là phần tốn thời gian nhất của bài. Làm ngay trong lúc sửa từng ảnh, đừng để dồn đến cuối.

3. Không có cách nào biết ảnh nào máy làm sai, ngoài việc tự nhìn.

Máy tự chấm độ tin cậy cho nó ở mức gần như tuyệt đối trên cả 500 ảnh, kể cả những ảnh mà điểm rơi lệch hẳn khỏi khuôn mặt. Nghĩa là không có sẵn danh sách "ảnh cần chú ý". Ảnh nào cũng phải mở ra xem.

### 1.2. Không tự nạp annotation lên task

BTC đã nạp sẵn ảnh và điểm gợi ý vào task của từng nhóm. Bạn chỉ mở task ra làm, không cần và không nên dùng chức năng upload annotation.

Thao tác đó ghi đè toàn bộ dữ liệu đang có trên task, nên mọi thứ nhóm đã sửa sẽ mất. Nếu thấy task trống hoặc thiếu điểm, báo mentor thay vì tự nạp file.

## 2. Quy ước

### 2.1. Trái và phải

Bài này xác định trái/phải theo CÁCH NHÌN TRÊN ẢNH, không theo giải phẫu của người. longmaytrai và mattrai là các vùng nằm về phía trái của khuôn mặt khi quan sát ảnh; longmayphai và matphai nằm về phía phải. Với mặt gần chính diện, các point của nhóm *trai có toạ độ x nhỏ hơn nhóm *phai.

Cách xác định: nhìn trực tiếp bố cục khuôn mặt trên ảnh và giữ thứ tự không gian trái → phải của các nhóm landmark. Không dùng trái/phải giải phẫu của người để đổi tên label. Không chia đôi toàn bộ frame một cách máy móc nếu khuôn mặt lệch khỏi tâm ảnh; tham chiếu là phía trái/phải của KHUÔN MẶT được nhìn thấy trên ảnh.

Khi mặt nghiêng mạnh, vẫn GIỮ NGUYÊN quy ước theo khung hình/khuôn mặt trên ảnh. Không chuyển sang convention giải phẫu giữa chừng. Nếu một vùng bị che đến mức khó xác định, xử lý theo rule Visible/Occluded/Outside hoặc mở Issue; không đổi tên mattrai ↔ matphai để “khớp giải phẫu”.

HumanPose-17 của bộ bài hiện tại cũng đã được chuẩn hoá theo quy ước trái/phải của khung hình VinFast. Vì vậy học viên có thể dùng cùng một nguyên tắc Left/Right xuyên suốt hai bài.

### 2.2. Point ID

ID chạy liên tục 0–49 qua cả 7 skeleton, không reset theo từng skeleton. mattrai dùng 14–21 chứ không phải 0–7.

Lưu ý: Point ID là chuẩn của bộ dữ liệu hiện tại và phải giữ nguyên khi import/pre-annotation. Không remap theo WFLW, InsightFace, COCO hay một schema face landmark khác.

| Skeleton | Point ID | Số điểm | Contour |
|---|---|---|---|
| longmaytrai | 0 – 4 | 5 | hở |
| longmayphai | 5 – 9 | 5 | hở |
| songmui | 10 – 13 | 4 | hở |
| mattrai | 14 – 21 | 8 | kín |
| matphai | 22 – 29 | 8 | kín |
| moingoai | 30 – 41 | 12 | kín |
| moitrong | 42 – 49 | 8 | kín |

Tên label viết liền, không dấu, không viết hoa, và không được đổi.

### 2.3. Sơ đồ point ID

In sơ đồ này ra và để cạnh màn hình khi làm việc.

## 3. Định nghĩa điểm

Cột "Tỉ lệ" là vị trí trung vị đo trên 500 ảnh pre-label, dùng để kiểm tra khoảng chia giữa các điểm. 0,00 là điểm đầu chuỗi, 1,00 là điểm cuối chuỗi.

Các mô tả chi tiết ở Mục 3 được dùng như QUY TẮC VẬN HÀNH cho bộ pre-label hiện tại: chúng tổng hợp topology, hình minh hoạ và thống kê trên dữ liệu. Khi wording ngắn trong guideline nguồn không mô tả đủ từng point, ưu tiên mapping đã được kiểm tra trên pre-label + sơ đồ point ID của bài.

### 3.1. Lông mày

Mỗi bên gồm 4 điểm trên bờ trên của lông mày và 1 điểm ở đuôi ngoài. Bờ trên là ranh giới giữa lông mày và da trán. Đặt điểm lên mép lông, không đặt vào giữa đám lông và không đặt lên da trán.

longmaytrai chạy từ ngoài vào trong:

| ID | Vị trí giải phẫu | Tỉ lệ |
|---|---|---|
| 0 | Đuôi ngoài, nơi lông mày thon lại về phía thái dương. Điểm này thấp và lệch ra ngoài so với điểm 1 | 0,00 |
| 1 | Bờ trên, đoạn ngoài | 0,15 |
| 2 | Bờ trên, đoạn giữa-ngoài | 0,41 |
| 3 | Bờ trên, đoạn giữa-trong, thường gần đỉnh cung | 0,73 |
| 4 | Đầu trong, gần sống mũi nhất | 1,00 |

longmayphai là ảnh gương, chạy ngược lại từ trong ra ngoài:

| ID | Vị trí giải phẫu | Tỉ lệ |
|---|---|---|
| 5 | Đầu trong, gần sống mũi | 0,00 |
| 6 | Bờ trên, đoạn giữa-trong | 0,26 |
| 7 | Bờ trên, đoạn giữa, thường gần đỉnh cung | 0,58 |
| 8 | Bờ trên, đoạn ngoài | 0,85 |
| 9 | Đuôi ngoài | 1,00 |

Khi mặt gần chính diện, toạ độ x của 10 điểm này tăng dần liên tục từ 0 đến 9. Nếu có điểm phá vỡ thứ tự, kiểm tra lại xem có gán nhầm nhóm hoặc nhầm thứ tự không.

### 3.2. Sống mũi

Bốn điểm chia đều dọc sống mũi. Ba đoạn 10–11, 11–12, 12–13 gần bằng nhau; tỉ lệ đoạn dài nhất trên đoạn ngắn nhất đo được trên pre-label là 1,01.

| ID | Vị trí giải phẫu | Tỉ lệ |
|---|---|---|
| 10 | Đỉnh sống mũi, điểm lõm giữa hai mắt, ngang tầm khoé mắt trong | 0,00 |
| 11 | Một phần ba trên sống mũi | 0,34 |
| 12 | Hai phần ba sống mũi | 0,67 |
| 13 | Chân sống mũi, nơi sống mũi kết thúc và đầu mũi bắt đầu nhô ra | 1,00 |

Điểm 13 không phải đỉnh mũi. Đo trên dữ liệu, điểm 13 nằm ở khoảng 72% quãng đường từ điểm 10 xuống đường nối hai cánh mũi, tức phía trên lỗ mũi và chưa chạm chóp mũi.

### 3.3. Mắt

Contour kín 8 điểm gồm 2 khoé, 3 điểm mí trên và 3 điểm mí dưới. Quy tắc chung cho cả hai mắt: index bắt đầu ở điểm trái nhất của mắt, chạy dọc mí trên sang phải đến điểm phải nhất, rồi vòng về theo mí dưới.

mattrai, điểm trái nhất là khoé ngoài:

| ID | Vị trí giải phẫu | Tỉ lệ |
|---|---|---|
| 14 | Khoé mắt ngoài, phía thái dương | 0,00 |
| 15 | Mí trên, một phần tư ngoài | 0,21 |
| 16 | Mí trên, giữa, điểm cao nhất | 0,48 |
| 17 | Mí trên, một phần tư trong | 0,76 |
| 18 | Khoé mắt trong, phía mũi | 1,00 |
| 19 | Mí dưới, một phần tư trong | 0,76 |
| 20 | Mí dưới, giữa, điểm thấp nhất | 0,50 |
| 21 | Mí dưới, một phần tư ngoài | 0,24 |

matphai, điểm trái nhất là khoé trong:

| ID | Vị trí giải phẫu | Tỉ lệ |
|---|---|---|
| 22 | Khoé mắt trong, phía mũi | 0,00 |
| 23 | Mí trên, một phần tư trong | 0,23 |
| 24 | Mí trên, giữa | 0,51 |
| 25 | Mí trên, một phần tư ngoài | 0,79 |
| 26 | Khoé mắt ngoài, phía thái dương | 1,00 |
| 27 | Mí dưới, một phần tư ngoài | 0,78 |
| 28 | Mí dưới, giữa | 0,52 |
| 29 | Mí dưới, một phần tư trong | 0,25 |

Điểm đặt trên bờ mi, tức ranh giới giữa da mi và nhãn cầu, nơi lông mi mọc ra. Không đặt lên lông mi, không đặt vào lòng trắng.

Bốn điều kiện đúng với mọi mắt, đo được trên toàn bộ 500 ảnh pre-label:

- Điểm đầu chuỗi, 14 hoặc 22, có toạ độ x nhỏ nhất trong 8 điểm.

- Điểm khoé còn lại, 18 hoặc 26, có toạ độ x lớn nhất.

- Mỗi điểm mí trên cao hơn hoặc bằng điểm mí dưới đối diện: 15 với 21, 16 với 20, 17 với 19, và 23 với 29, 24 với 28, 25 với 27.

- Contour không có đường bắt chéo tạo thành hình chữ X.

### 3.4. Môi

moingoai là contour kín 12 điểm dọc đường viền môi, tức ranh giới giữa phần môi đỏ và vùng da quanh miệng.

| ID | Vị trí giải phẫu | Tỉ lệ |
|---|---|---|
| 30 | Khoé miệng trái | 0,00 |
| 31 – 35 | Bờ môi trên, từ khoé trái sang khoé phải | 0,18 · 0,41 · 0,53 · 0,65 · 0,85 |
| 36 | Khoé miệng phải | 1,00 |
| 37 – 41 | Bờ môi dưới, từ khoé phải về khoé trái | 0,87 · 0,72 · 0,55 · 0,35 · 0,18 |

Điểm 33 và 39 gần chính giữa miệng nhất, dùng làm mốc khi chia khoảng.

moitrong là contour kín 8 điểm dọc mép trong của môi, tức ranh giới môi với khoang miệng.

| ID | Vị trí giải phẫu | Tỉ lệ |
|---|---|---|
| 42 | Khoé trong trái | 0,00 |
| 43 – 45 | Mép trong môi trên | 0,22 · 0,53 · 0,82 |
| 46 | Khoé trong phải | 1,00 |
| 47 – 49 | Mép trong môi dưới | 0,81 · 0,53 · 0,23 |

moitrong luôn nằm hoàn toàn bên trong moingoai: toạ độ x của điểm 42 lớn hơn điểm 30, và điểm 46 nhỏ hơn điểm 36.

## 4. Trạng thái điểm

Ba trạng thái, dùng đúng property có sẵn của CVAT. Không tạo attribute mới. Không dùng Hidden thay cho Outside, vì Hidden chỉ ẩn hiển thị trên giao diện chứ không lưu vào dữ liệu.

| Trạng thái | Cấu hình CVAT | Điều kiện | Toạ độ |
|---|---|---|---|
| Visible | outside = 0, occluded = 0 | Nhìn thấy trực tiếp | Phải đúng |
| Occluded | occluded = 1 | Bị che nhưng còn suy ra được vị trí | Phải đúng theo ước lượng |
| Outside | outside = 1 | Ngoài khung hình, hoặc bị che đến mức không còn căn cứ ước lượng | Không dùng đến |

### 4.1. Quy tắc quyết định cho từng điểm

Mục tiêu là quyết định trạng thái dựa trên khả năng quan sát/suy luận của landmark thật, không dựa trên confidence của model. Với pre-label sai vị trí, phải sửa geometry trước hoặc đồng thời với trạng thái; không được giữ điểm sai chỉ vì model đã đặt sẵn.

Áp dụng theo thứ tự:

- Điểm có nằm trong khung hình không? Không thì Outside.

- Có nhìn thấy trực tiếp không? Có thì Visible.

- Có suy ra được vị trí từ hai điểm liền kề trong contour không? Có thì Occluded, không thì Outside.

Không dùng det_confidence hay quality.status để quyết định trạng thái. Hai trường này bằng nhau ở mọi ảnh.

### 4.2. Ngưỡng quyết định cho cả skeleton

Trong bảng dưới, rule mắt ≥4/8 là rule được nêu rõ trong guideline VF. Các ngưỡng cho lông mày/môi là ngưỡng vận hành của bộ bài hiện tại để thống nhất correction; nếu mentor/BTC ban hành rule mới thì ưu tiên rule mới.

Áp dụng khi cả một bộ phận bị che, thay vì xét từng điểm:

| Skeleton | Còn nhìn thấy | Xử lý |
|---|---|---|
| mattrai, matphai | Từ 4/8 điểm trở lên | Đặt đủ contour, điểm không thấy đánh Occluded |
| mattrai, matphai | Dưới 4/8 điểm | Outside cả skeleton |
| longmaytrai, longmayphai | Từ 3/5 điểm trở lên | Đặt đủ, điểm không thấy đánh Occluded |
| longmaytrai, longmayphai | Dưới 3/5 điểm | Outside cả skeleton |
| moingoai | Từ 6/12 điểm trở lên | Đặt đủ |
| moitrong | Từ 4/8 điểm trở lên | Đặt đủ |
| songmui | Chỉ Outside khi cả sống mũi khuất |  |

## 5. Quy trình

Bài chia làm hai phần và cách làm khác nhau:

| Phần | Số ảnh | Label schema | Điểm landmark |
|---|---|---|---|
| A | 50 | BTC cấu hình sẵn trong task | Đã có sẵn trên task, chỉ sửa |
| B | 20 | Nhóm tự dựng | Nhóm tự vẽ từ đầu |

### 5.1. Phần A — 50 ảnh có pre-label

- Mở đúng task được phân công, đối chiếu mã nhóm. Ảnh và điểm gợi ý đã có sẵn.

- Chạy kiểm tra ở mục 5.2 trên 5 ảnh đầu. Nếu có mục nào không đạt thì dừng và báo mentor, chưa sửa hàng loạt.

- Sửa từng ảnh theo thứ tự ở mục 5.5.

- Tự kiểm tra theo mục 7 rồi nộp.

### 5.2. Kiểm tra 5 ảnh đầu trước khi làm hàng loạt

Mở 5 ảnh đầu của task và soát:

- Có đủ 7 skeleton trên mỗi frame.

- Không có label Face, đúng như thiết kế.

- Hai mắt tạo thành vòng kín, không có đường bắt chéo.

- mattrai nằm ở nửa trái khung hình.

- Toạ độ x của các điểm 0 đến 9 tăng dần.

- moitrong nằm trong moingoai.

- Không có điểm nào rơi ra ngoài khuôn mặt.

### 5.3. Phần B — đối chiếu label schema

Schema 7 skeleton đã dựng sẵn ở project của nhóm và dùng chung cho cả bốn task. Việc của nhóm ở phần B là đối chiếu schema đó với đặc tả trước khi vẽ, không phải dựng lại.

Cả bốn task dùng chung một bộ Labels ở cấp project nên không ai được sửa; sửa một sublabel là đổi luôn cho phần A. Phân công một người đối chiếu, báo cả nhóm kết quả rồi mới bắt đầu vẽ.

Đối chiếu xong báo mentor trước khi vẽ hàng loạt. Thấy sai thì báo, tuyệt đối không tự đổi tên sublabel: đổi sau khi đã vẽ sẽ làm mất annotation đã có.

Cách 1 — xem trong phần Labels của project. Làm lần lượt cho từng skeleton trong bảng ở mục 2.2:

- Mở Labels của project, tìm label đúng tên như bảng, xác nhận kiểu là Skeleton.

- Xem các node trên khung vẽ có đúng hình dạng thật của bộ phận không, tham chiếu sơ đồ ở mục 2.3.

- Soát các cạnh nối giữa các node theo đúng thứ tự point ID.

- Soát tên từng sublabel là point ID toàn cục dạng chuỗi số: mattrai có sublabel tên 14 đến 21, không phải 0 đến 7.

- Xong skeleton này thì sang skeleton sau.

Số node và số cạnh phải khớp bảng này:

| Skeleton | Sublabel | Số node | Số cạnh | Nối |
|---|---|---|---|---|
| longmaytrai | 0 … 4 | 5 | 4 | 0-1-2-3-4, hở hai đầu |
| longmayphai | 5 … 9 | 5 | 4 | 5-6-7-8-9, hở hai đầu |
| songmui | 10 … 13 | 4 | 3 | 10-11-12-13, hở hai đầu |
| mattrai | 14 … 21 | 8 | 8 | 14→21 rồi 21 nối về 14, vòng kín |
| matphai | 22 … 29 | 8 | 8 | 22→29 rồi 29 nối về 22, vòng kín |
| moingoai | 30 … 41 | 12 | 12 | 30→41 rồi 41 nối về 30, vòng kín |
| moitrong | 42 … 49 | 8 | 8 | 42→49 rồi 49 nối về 42, vòng kín |

Tổng 50 node và 47 cạnh trên 7 skeleton.

Cách 2 — mở tab Raw để đọc JSON. Những điểm CVAT bắt buộc, dùng để soi lại cả 7 skeleton:

- Mỗi label có "type": "skeleton" và "attributes": [].

- Mỗi sublabel có "type": "points" và "attributes": [].

- Có trường "svg" hợp lệ, trong đó mỗi node là một thẻ circle mang data-label-name trùng tên sublabel, mỗi cạnh là một thẻ line mang data-node-from và data-node-to.

Không thêm occluded hay outside vào Raw để tạo dropdown. Hai trường này là trạng thái của annotation, không phải attribute của ontology.

Schema đối chiếu nằm ở mục 10. Dùng nó để so với schema đang có trong project; chỉ mentor mới được sửa.

Đối chiếu đủ các mục sau:

- Đủ 7 label, tên viết đúng tuyệt đối, không có label Face.

- Tổng 50 sublabel, tên là số từ 0 đến 49, không trùng, không thiếu.

- Bốn skeleton mattrai, matphai, moingoai, moitrong là vòng kín; ba skeleton còn lại hở hai đầu.

- Thử đặt một skeleton lên ảnh bất kỳ, xem hình dạng mẫu có giống bộ phận thật không.

Hai lỗi schema hay gặp, thấy thì báo mentor:

| Thông báo | Nguyên nhân | Cách sửa |
|---|---|---|
| attributes must be an array | Thiếu "attributes": [] ở label hoặc sublabel | Thêm vào cả hai cấp |
| skeletons must provide a correct SVG template | Thiếu svg, hoặc node trong svg không khớp tên sublabel | Dựng lại node và cạnh, đối chiếu tên sublabel |

### 5.4. Phần B — vẽ từ đầu

- Chọn công cụ Skeleton và label cần vẽ.

- Đặt điểm theo thứ tự point ID, tuân thủ mục 5.5.

- Đặt trạng thái cho từng điểm.

- Lưu trước khi sang ảnh tiếp theo.

Không vẽ bounding box Face, schema của bài không dùng.

Sau khi làm xong 2 ảnh đầu, đối chiếu với phần A để thống nhất cách đặt điểm giữa hai nửa dataset.

### 5.5. Thứ tự đặt điểm trong một ảnh

Dùng chung cho cả phần A và phần B:

- Kiểm tra trái phải. Sai thì sửa ngay, trước khi tinh chỉnh vị trí.

- Đặt 12 điểm neo: 0, 4, 5, 9, 10, 13, 14, 18, 22, 26, 30, 36. Các điểm này quyết định phần còn lại.

- Đặt các điểm contour giữa các neo, giữ khoảng chia theo tỉ lệ ở mục 3.

- Đặt trạng thái cho từng điểm.

- Lưu trước khi sang ảnh tiếp theo.

Zoom tối thiểu 200% khi đặt điểm mắt và môi trong. Ở mức 100%, 8 điểm của một mắt nằm gọn trong khoảng 25 px và không thể đặt chính xác.

## 6. Tình huống đặc biệt

### 6.1. Mặt nghiêng mạnh

Khi mặt quay nhiều, lông mày và mắt phía xa bị sống mũi và gò má che. Pre-label thường dồn cả cụm điểm về giữa mặt, cách vị trí thật khá xa. Trường hợp nghiêng nhất trong bộ có khoảng cách hai mắt tụt từ khoảng 96 px xuống 56 px.

Xử lý theo ngưỡng ở mục 4.2. Không giữ nguyên cụm điểm bị dồn rồi đánh Occluded, vì Occluded vẫn đòi toạ độ ước lượng đúng.

### 6.2. Nheo hoặc nhắm mắt

Contour vẫn giữ đủ 8 điểm và vẫn là vòng kín. Mí trên và mí dưới trùng nhau theo đường khe mí, nên các cặp 15 với 21, 16 với 20, 17 với 19 được phép cùng toạ độ y. Hai khoé mắt vẫn đặt đúng vị trí giải phẫu, không kéo sát vào nhau. Trạng thái là Visible nếu còn thấy đường khe mí, chỉ Occluded khi bị vật khác che.

### 6.3. Miệng mở

Khoảng 20% số ảnh có miệng hé hoặc mở. moitrong tách rõ khỏi moingoai và ôm theo khoang miệng thật. Nếu thấy răng hoặc lưỡi, đặt điểm lên mép môi chứ không lên răng. Làm điểm 44 và 48 trước rồi chia phần còn lại.

### 6.4. Miệng đóng

Chiếm 399 trong 500 ảnh, tức 80%, nên đây là trường hợp mặc định chứ không phải ngoại lệ.

moitrong vẫn giữ đủ 8 điểm, nằm dọc theo đường khép môi. Các cặp trên dưới đối diện, 43 với 49, 44 với 48, 45 với 47, được phép trùng hoặc gần trùng toạ độ. Trên pre-label, thứ tự trên dưới của moitrong chỉ giữ đúng ở 40% ảnh, phần còn lại là do môi khép nên hai đường chồng lên nhau.

Không xoá skeleton moitrong và không đặt Outside chỉ vì miệng đóng. Vẫn giữ ràng buộc moitrong nằm trong moingoai.

### 6.5. Kính

Người trong ảnh đeo kính ở gần như toàn bộ frame.

| Tình huống | Xử lý |
|---|---|
| Gọng cắt ngang mí trên nhưng vẫn thấy bờ mi hai bên | Đặt điểm lên bờ mi phía sau gọng, đánh Occluded |
| Gọng che hẳn đuôi lông mày | Ước lượng theo hướng đi của lông mày, đánh Occluded |
| Phản quang che kín vùng mắt, còn khoé mắt nhìn được | Ước lượng từ khoé mắt, đánh Occluded |
| Phản quang che kín, không còn khoé mắt nào nhìn được | Outside cả skeleton mắt |

Không đặt điểm lên gọng kính trong mọi trường hợp.

### 6.6. Đầu nghiêng

Góc nghiêng của đường nối hai mắt trong bộ ảnh dao động từ −21° đến +5°. Khi mặt nghiêng, trên dưới theo khung hình không còn khớp với trên dưới của khuôn mặt, dễ đảo mí trên với mí dưới.

Xác định mí trên và mí dưới theo giải phẫu khuôn mặt. Quy ước trái phải vẫn giữ theo khung hình như mục 2.1.

### 6.7. Tay, vô-lăng, dây an toàn che mặt

Xử lý như mục 6.1: che một phần thì Occluded kèm toạ độ ước lượng, che hoàn toàn một bộ phận thì Outside cả skeleton đó.

### 6.8. Ảnh nhoè

Đặt điểm ở tâm vệt nhoè. Nếu nhoè đến mức không phân biệt được mắt với lông mày, mở Issue và bỏ qua frame thay vì đoán.

### 6.9. Frame liên tiếp giống nhau

Mục này áp dụng cho 50 ảnh có pre-label: mỗi nhóm nhận 2 đến 3 dãy frame liên tiếp. 20 ảnh của phần B rải đều trên cả phiên, không liên tiếp nhau.

Không copy nguyên nhãn của frame trước mà không kiểm tra, vì điểm sẽ trôi dần khỏi vị trí đúng. Ngược lại, nhãn giữa hai frame liền kề phải mượt. Trên pre-label, độ dịch chuyển trung bình giữa hai frame liền kề là 2,7 px và phân vị 90 là 7,7 px. Nếu nhãn nhảy quá 15 px giữa hai frame liền kề mà trong ảnh không có chuyển động tương ứng, kiểm tra lại cả hai frame.

### 6.10. Mặt nhỏ hoặc ở rìa khung hình

Khoảng cách hai mắt nhỏ nhất trong bộ là 56 px, mức này cần zoom từ 300% trở lên. Điểm rơi ra ngoài biên ảnh đánh Outside.

### 6.11. Không có mặt hoặc có nhiều hơn một mặt

500 ảnh có pre-label đều có đúng một khuôn mặt. Nếu ở 20 ảnh tự làm gặp ảnh không có mặt, hoặc có mặt thứ hai như hành khách hay ảnh phản chiếu trong gương, mở Issue. Mặc định chỉ gán nhãn người lái.

### 6.12. Pre-label đã đúng

Nếu kiểm tra thấy hình học đúng thì giữ nguyên vị trí, nhưng vẫn phải đặt trạng thái cho cả 50 điểm. Giữ nguyên là một kết quả hợp lệ.

## 7. Tự kiểm tra trước khi nộp

### 7.1. Từng frame

- Đủ 7 skeleton và 50 điểm.

- mattrai và longmaytrai ở nửa trái khung hình.

- Toạ độ x của các điểm 0 đến 9 tăng dần khi mặt gần chính diện.

- Hai mắt là vòng kín, không bắt chéo.

- Mí trên cao hơn hoặc bằng mí dưới ở cả ba cặp đối diện của mỗi mắt.

- Điểm 13 nằm trên lỗ mũi, chưa chạm chóp mũi.

- Ba đoạn của songmui chia gần đều.

- moitrong nằm trong moingoai.

- Không có điểm nào nằm trên gọng kính, tóc hoặc nền phía sau.

- Mọi điểm đã có trạng thái.

- Điểm Occluded có toạ độ ước lượng hợp lý, không giữ nguyên vị trí sai của pre-label.

### 7.2. Cả job

- Đã làm đủ 70 ảnh.

- Đã đối chiếu schema ở phần B: đúng 7 label, 50 sublabel, tên trùng khít với phần A.

- Đã rà lại ít nhất 10 frame, trong đó có 1 frame nghiêng mạnh, 1 frame miệng mở, 1 frame nheo mắt, 1 frame kính loá.

- Đã lướt toàn bộ job theo thứ tự frame để phát hiện điểm nhảy bất thường.

- Mọi trường hợp không chắc đã mở Issue thay vì tự đặt luật mới.

## 8. Sai số cho phép

Chuẩn hoá theo IOD, tức khoảng cách giữa tâm hai mắt, trung vị khoảng 96 px trong bộ ảnh này.

| Nhóm điểm | Ngưỡng | Quy ra px |
|---|---|---|
| 12 điểm neo: 0, 4, 5, 9, 10, 13, 14, 18, 22, 26, 30, 36 | 3% IOD | khoảng 3 px |
| Các điểm contour còn lại | 5% IOD | khoảng 5 px |
| Sai số trung bình toàn ảnh (NME) | 0,035 | khoảng 3,4 px |

Các ngưỡng này là đề xuất khởi điểm, sẽ được chốt lại sau khi mentor hoàn thành bộ ảnh chuẩn.

## 9. Lỗi thường gặp

| Lỗi | Nguyên nhân | Xử lý |
|---|---|---|
| Đi tìm label Face không thấy | Tài liệu cũ mô tả sai | Schema không có Face, xem mục 1.1 |
| Đảo trái phải toàn bộ job | Dùng convention giải phẫu hoặc đổi convention khi mặt nghiêng | Giữ Left/Right theo khung hình/khuôn mặt trên ảnh, xem mục 2.1 |
| Mắt thành hình chữ X | Sai thứ tự nối điểm | Kiểm tra thứ tự 14→21 và 22→29 |
| Đặt điểm 13 ở chóp mũi | Không có định nghĩa trong tài liệu cũ | Điểm 13 là chân sống mũi, xem mục 3.2 |
| Xoá moitrong khi miệng đóng | Tưởng là lỗi | Miệng đóng chiếm 80% số ảnh, xem mục 6.4 |
| Đặt điểm lên gọng kính | Gọng dễ nhìn hơn bờ mi | Luôn đặt lên bờ mi thật rồi đánh Occluded, xem mục 6.5 |
| Quên đặt trạng thái | Pre-label đã gán visible sẵn nên trông như đã xong | Phải đặt mới toàn bộ, xem mục 1.1 |
| Reset point ID theo từng skeleton | Hiểu nhầm về skeleton | ID toàn cục 0–49, xem mục 2.2 |
| Tự nạp annotation rồi mất hết công | Upload ghi đè dữ liệu trên task | Không dùng upload annotation, xem mục 1.2 |
| Copy nhãn giữa các frame liên tiếp | Ảnh gần giống nhau | Xem mục 6.9 |
| Schema phần B đặt sublabel là 0–7 cho mỗi skeleton | Reset ID theo từng skeleton | Dùng point ID toàn cục, xem mục 5.3 |
| Hai người cùng sửa Labels, schema bị ghi đè | Không phân công ai dựng | Một người dựng, cả nhóm kiểm tra, xem mục 5.3 |
| Chia đôi toàn bộ frame để xác định trái/phải | Khuôn mặt có thể lệch khỏi tâm ảnh | Xác định trái/phải theo bố cục của khuôn mặt trên ảnh, không theo tâm frame |

Ghi chú nguồn: guideline học viên giữ các mô tả chi tiết/threshold hữu ích từ bản cũ, nhưng đã sửa toàn bộ convention Left/Right để đồng bộ VinFast theo khung hình và giữ nguyên thiết kế hiện tại KHÔNG có Face bbox.

## 10. Phụ lục — schema đối chiếu

Dùng để kiểm tra lại schema tự dựng ở mục 5.3. Chỉ dán thẳng vào tab Raw khi mentor cho phép.

File: schema/vf50_labels_raw.json

Cấu trúc rút gọn, phần svg lược bớt cho dễ đọc:

[
  {
    "name": "longmaytrai",
    "type": "skeleton",
    "attributes": [],
    "sublabels": [
      { "name": "0", "type": "points", "attributes": [] },
      { "name": "1", "type": "points", "attributes": [] },
      { "name": "2", "type": "points", "attributes": [] },
      { "name": "3", "type": "points", "attributes": [] },
      { "name": "4", "type": "points", "attributes": [] }
    ],
    "svg": "<line ... data-type=\"edge\" data-node-from=\"1\" data-node-to=\"2\"></line> ... <circle ... data-type=\"element node\" data-element-id=\"1\" data-node-id=\"1\" data-label-name=\"0\"></circle> ..."
  }
]

Sáu skeleton còn lại theo đúng khuôn này, chỉ khác tên label và dải tên sublabel.

Ba quy tắc rút ra từ schema, dùng để tự kiểm tra:

- data-label-name của mỗi circle phải trùng tên một sublabel, và thứ tự các circle trùng thứ tự sublabel.

- data-node-id chạy liên tục từ 1 đến số điểm của skeleton đó. Đây là số thứ tự trong skeleton, khác với tên sublabel vốn là point ID toàn cục.

- data-node-from và data-node-to của mỗi line chỉ nhận giá trị trong dải data-node-id nói trên.

---

## Nguồn: `Week2_Guideline_HumanPose17_HocVien_v1.1.docx`

# Guideline gán nhãn — HumanPose-17 Body Keypoints

Dành cho học viên. Phiên bản 1.1, Week 2, áp dụng cho 10 nhóm G01–G10. Cập nhật quy ước Left/Right theo khung hình VinFast.

## 1. Thông tin bài

Đặt 17 keypoint lên cơ thể người lái trong cabin xe, dưới dạng một skeleton tên person.

| Phần | Số ảnh mỗi nhóm | Việc phải làm |
|---|---|---|
| Có pre-label | 40 | Sửa vị trí điểm có sẵn, đặt trạng thái |
| Không pre-label | 20 | Tự dựng schema, đặt cả 17 điểm từ đầu |
| Tổng | 60 |  |

Ảnh 960 × 540. Dữ liệu trải trên 15 người lái và 29 đoạn quay khác nhau.

### 1.1. Bốn điều cần biết trước khi bắt đầu

1. Ảnh bị xoay 90°.

Người lái nằm ngang trong ảnh: đầu ở bên trái, chân ở bên phải. Nghĩa là "phía trên" của ảnh không phải "phía trên" của cơ thể. Mỗi lần mở một ảnh mới, nhìn xác định đâu là đầu đâu là chân trước rồi mới đặt điểm.

2. Sẽ thấy một chùm điểm chồng lên nhau ở góc trên-trái ảnh.

Đó là những khớp máy không đoán được nên vứt tạm vào góc. Toạ độ đó vô nghĩa, không phải vị trí thật của khớp. Có ở 68% số ảnh.

Với mỗi điểm như vậy, bạn nhìn ảnh, tự tìm xem khớp đó ở đâu, rồi kéo về đúng chỗ hoặc đánh Outside nếu không thấy. Không kéo đại cho gần gần. Chi tiết ở mục 6.1.

3. Máy sai nhiều nhất ở chân và tai.

Trong 400 ảnh có điểm gợi ý: điểm 4 (R Ear) hỏng 220 lần, điểm 16 (R Ankle) 118 lần, điểm 17 (L Ankle) 82 lần. Những chỗ này coi như làm lại từ đầu, đừng mất công chỉnh nhẹ vài pixel.

4. Chỉ gán nhãn người lái.

Một số ảnh có hành khách hoặc người ngồi ghế sau lọt vào khung. Bỏ qua họ, trừ khi mentor nói khác.

### 1.2. Không tự nạp annotation lên task

BTC đã nạp sẵn ảnh và điểm gợi ý vào task của từng nhóm. Bạn chỉ mở task ra làm, không cần và không nên dùng chức năng upload annotation.

Thao tác đó ghi đè toàn bộ dữ liệu đang có trên task, nên mọi thứ nhóm đã sửa sẽ mất. Nếu thấy task trống hoặc thiếu điểm, báo mentor thay vì tự nạp file.

## 2. Quy ước

### 2.1. Trái và phải

Bài này xác định trái/phải theo KHUNG HÌNH, theo đúng quy ước VinFast. Điểm R nằm ở phía phải của ảnh đang hiển thị; điểm L nằm ở phía trái của ảnh. Không suy luận theo tay/chân giải phẫu của người lái.

Cách xác định, làm đúng thứ tự:

- Nhìn trực tiếp khung ảnh đang hiển thị trên CVAT.

- Xác định nửa trái và nửa phải của khung hình, bất kể người lái quay mặt, quay lưng hay ảnh bị xoay 90°.

- Gán các điểm R_* ở phía phải khung hình và các điểm L_* ở phía trái khung hình theo đúng số thứ tự VF.

Mẹo kiểm tra nhanh: với một người nhìn thẳng, các điểm chẵn 2, 4, 6, 8, 10, 12, 14, 16 nằm về phía phải khung hình; các điểm lẻ tương ứng 3, 5, 7, 9, 11, 13, 15, 17 nằm về phía trái khung hình. Đây chỉ là kiểm tra topology, không thay cho việc đặt đúng khớp thực tế.

Bài VF-50 Face Landmark của cùng tuần cũng dùng quy ước trái/phải theo phía của khung hình. Vì vậy hai bài HumanPose-17 và Face Landmark dùng cùng một quy ước Left/Right.

### 2.2. Danh sách keypoint

Thứ tự điểm không được đổi. Trên CVAT, sublabel dùng số 1 đến 17 để khớp trực tiếp với guideline VinFast và Raw schema của bài.

| Index | Tên | Index | Tên |
|---|---|---|---|
| 1 | Nose | 10 | R Wrist |
| 2 | R Eye | 11 | L Wrist |
| 3 | L Eye | 12 | R Hip |
| 4 | R Ear | 13 | L Hip |
| 5 | L Ear | 14 | R Knee |
| 6 | R Shoulder | 15 | L Knee |
| 7 | L Shoulder | 16 | R Ankle |
| 8 | R Elbow | 17 | L Ankle |
| 9 | L Elbow |  |  |

### 2.3. Sơ đồ keypoint

In sơ đồ này ra và để cạnh màn hình khi làm việc.

## 3. Định nghĩa điểm

Nguyên tắc chung: điểm đánh dấu khớp và đặt ở tâm khớp, không đặt lên quần áo hay mép ngoài chi.

### 3.1. Vùng đầu

| # | Tên | Vị trí theo guideline VF |
|---|---|---|
| 1 | Nose | Chóp mũi. Mặt nghiêng vẫn là chóp mũi, không dời về giữa mặt. |
| 2 | R Eye | Tâm đồng tử của mắt nằm phía PHẢI khung hình. Mắt nhắm thì đặt ở tâm khe mí. |
| 3 | L Eye | Tâm đồng tử của mắt nằm phía TRÁI khung hình. Mắt nhắm thì đặt ở tâm khe mí. |
| 4 | R Ear | Ống tai nằm phía PHẢI khung hình, không phải chóp vành tai hay dái tai. |
| 5 | L Ear | Ống tai nằm phía TRÁI khung hình, không phải chóp vành tai hay dái tai. |

Khi tóc phủ kín tai, nếu còn ước lượng được vị trí ống tai từ đường viền hàm và thái dương thì đặt điểm rồi đánh Occluded, không thì Outside. R/L của tai vẫn xác định theo phía khung hình.

### 3.2. Chi trên

| # | Tên | Vị trí theo guideline VF |
|---|---|---|
| 6 | R Shoulder | Tâm khớp vai nằm phía PHẢI khung hình, tại điểm xoay của cánh tay. |
| 7 | L Shoulder | Tâm khớp vai nằm phía TRÁI khung hình. |
| 8 | R Elbow | Tâm khớp khuỷu nằm phía PHẢI khung hình. |
| 9 | L Elbow | Tâm khớp khuỷu nằm phía TRÁI khung hình. |
| 10 | R Wrist | Tâm khớp cổ tay nằm phía PHẢI khung hình, ở nếp gấp cổ tay. |
| 11 | L Wrist | Tâm khớp cổ tay nằm phía TRÁI khung hình. |

Tay đặt trên vô-lăng là tư thế thường gặp nhất của bài. Cổ tay vẫn đặt ở nếp gấp cổ tay, không dời lên vành vô-lăng. R/L xác định theo phía khung hình, không theo tay giải phẫu của người lái.

### 3.3. Chi dưới

Đây là vùng pre-label sai nhiều nhất, vì trong cabin chi dưới thường khuất sau vô-lăng, bảng táp-lô, ghế, hoặc nằm ngoài khung hình.

| # | Tên | Vị trí theo guideline VF |
|---|---|---|
| 12 | R Hip | Tâm khớp háng nằm phía PHẢI khung hình, không phải mép ngoài hông hay cạp quần. |
| 13 | L Hip | Tâm khớp háng nằm phía TRÁI khung hình. |
| 14 | R Knee | Tâm khớp gối nằm phía PHẢI khung hình, giữa xương bánh chè. |
| 15 | L Knee | Tâm khớp gối nằm phía TRÁI khung hình. |
| 16 | R Ankle | Tâm khớp cổ chân nằm phía PHẢI khung hình, ngang mắt cá. |
| 17 | L Ankle | Tâm khớp cổ chân nằm phía TRÁI khung hình. |

Cách quyết định khi chi dưới bị che:

| Nhìn thấy được gì | Xử lý cho gối và cổ chân |
|---|---|
| Thấy đường đùi hoặc cẳng chân qua quần | Occluded, ước lượng theo trục chi |
| Chỉ thấy hông, chi dưới khuất hẳn | Outside |
| Chi dưới bị khung hình cắt | Outside |

Không đặt điểm lên ghế, cần số hay sàn xe chỉ vì cần chỗ để đặt. Không ước lượng vị trí gối và cổ chân chỉ dựa vào tỉ lệ cơ thể khi không thấy bất cứ phần nào của chi.

## 4. Trạng thái điểm

Ba trạng thái, dùng đúng property có sẵn của CVAT. Không tạo attribute mới. Không dùng Hidden thay cho Outside, vì Hidden chỉ ẩn hiển thị trên giao diện chứ không lưu vào dữ liệu.

| Trạng thái | Cấu hình CVAT | Điều kiện | Toạ độ |
|---|---|---|---|
| Visible | outside = 0, occluded = 0 | Nhìn thấy trực tiếp khớp | Phải đúng |
| Occluded | occluded = 1 | Bị che nhưng còn suy ra được vị trí | Phải đúng theo ước lượng |
| Outside | outside = 1 | Ngoài khung hình, hoặc bị che đến mức không còn căn cứ ước lượng | Không dùng đến |

### 4.1. Quy tắc quyết định

Áp dụng theo thứ tự:

- Khớp có nằm trong khung hình không? Không thì Outside.

- Có nhìn thấy trực tiếp không? Có thì Visible.

- Có suy ra được vị trí từ các khớp liền kề, tư thế và tỉ lệ cơ thể không? Có thì Occluded và đặt điểm ở vị trí ước lượng, không thì Outside.

Không dùng confidence để quyết định trạng thái. Confidence thấp có thể do che khuất, do ra ngoài khung, do nhoè, hoặc do mô hình đoán sai.

Khi không chắc, chọn Outside. Một điểm Outside trung thực tốt hơn một điểm Occluded đặt sai cả trăm pixel.

## 5. Quy trình

Bài chia làm hai phần và cách làm khác nhau:

| Phần | Số ảnh | Label schema | Keypoint |
|---|---|---|---|
| A | 40 | BTC cấu hình sẵn trong task | Đã có sẵn trên task, chỉ sửa |
| B | 20 | Nhóm tự dựng | Nhóm tự vẽ từ đầu |

### 5.1. Phần A — 40 ảnh có pre-label

- Mở đúng task được phân công, đối chiếu mã nhóm. Ảnh và điểm gợi ý đã có sẵn.

- Chạy kiểm tra ở mục 5.2 trên 5 ảnh đầu. Nếu có mục nào không đạt thì dừng và báo mentor.

- Sửa từng ảnh theo thứ tự ở mục 5.5.

- Tự kiểm tra theo mục 7 rồi nộp.

### 5.2. Kiểm tra 5 ảnh đầu trước khi làm hàng loạt

- Có skeleton person với đủ 17 sublabel, được đánh số 1 đến 17.

- Số skeleton khớp số người cần gán, mặc định là một người lái.

- Không có skeleton nào lệch toàn bộ so với người trong ảnh.

- Đã nhận ra chùm điểm ở góc trên-trái.

- Trái/phải chưa bị đảo: R ở phía phải khung hình, L ở phía trái khung hình.

### 5.3. Phần B — đối chiếu label schema

Schema đã dựng sẵn ở project của nhóm và dùng chung cho cả bốn task. Đó là skeleton person; việc của nhóm ở phần B là đối chiếu schema đó với đặc tả trước khi vẽ, không phải dựng lại.

Cả bốn task dùng chung một bộ Labels ở cấp project nên không ai được sửa; sửa một sublabel là đổi luôn cho phần A. Phân công một người đối chiếu, báo cả nhóm kết quả rồi mới bắt đầu vẽ.

Đối chiếu xong báo mentor trước khi vẽ hàng loạt. Thấy sai thì báo, tuyệt đối không tự đổi tên sublabel: đổi sau khi đã vẽ sẽ làm mất annotation đã có.

Cách 1 — xem trong phần Labels của project:

- Mở Labels của project, tìm label tên person, xác nhận kiểu là Skeleton.

- Xem 17 node trên khung vẽ có đúng dáng người đứng nhìn thẳng không, tham chiếu sơ đồ ở mục 2.3.

- Soát 17 cạnh theo bảng dưới.

- Soát tên từng sublabel là số 1, 2, …, 17 đúng như danh sách ở mục 2.2. Không dùng L_* / R_* trong schema của bài này.

- Lưu.

Các cạnh cần nối theo topology VF:

| Vùng | Cạnh |
|---|---|
| Đầu | 1–2, 1–3, 2–4, 3–5, (đầu - thân): 4-6, 5-7 |
| Thân | 6–7, 6–12, 7–13, 12–13 |
| Tay | 6–8, 8–10, 7–9, 9–11 |
| Chân | 12–14, 14–16, 13–15, 15–17 |

Khi soát node, nhớ rằng R/L theo khung hình. Với dáng người nhìn thẳng trong trình vẽ, các node R (2,4,6,8,10,12,14,16) nằm ở nửa phải; các node L (3,5,7,9,11,13,15,17) nằm ở nửa trái.

Cách 2 — mở tab Raw để đọc JSON. Những điểm CVAT bắt buộc, dùng để soi lại schema:

- Label có "type": "skeleton" và "attributes": [].

- Mỗi sublabel có "type": "points" và "attributes": [].

- Có trường "svg" hợp lệ, trong đó mỗi node là một thẻ circle mang data-label-name trùng đúng số sublabel ("1"…"17"), mỗi cạnh là một thẻ line mang data-node-from và data-node-to.

Không thêm occluded hay outside vào Raw để tạo dropdown. Hai trường này là trạng thái của annotation, không phải attribute của ontology.

Schema đối chiếu nằm ở mục 10. Dùng nó để so với schema đang có trong project; chỉ mentor mới được sửa.

Đối chiếu đủ các mục sau:

- Một label person, đủ 17 sublabel từ 1 đến 17, không thừa không thiếu.

- Thứ tự sublabel đúng như mục 2.2.

- Đủ các cạnh theo bảng topology; mỗi tay và mỗi chân tạo thành chuỗi liền mạch.

- Thử đặt một skeleton lên ảnh bất kỳ, xem hình dạng mẫu có giống dáng người không.

Hai lỗi schema hay gặp, thấy thì báo mentor:

| Thông báo | Nguyên nhân | Cách sửa |
|---|---|---|
| attributes must be an array | Thiếu "attributes": [] ở label hoặc sublabel | Thêm vào cả hai cấp |
| skeletons must provide a correct SVG template | Thiếu svg, hoặc node trong svg không khớp tên sublabel | Dựng lại node và cạnh, đối chiếu tên sublabel |

### 5.4. Phần B — vẽ từ đầu

- Xác định phía trái/phải của KHUNG HÌNH trước khi đặt điểm đầu tiên. Không cần suy luận trái/phải giải phẫu của người lái.

- Chọn công cụ Skeleton và label person.

- Đặt điểm theo thứ tự ở mục 5.5.

- Đặt trạng thái cho cả 17 điểm.

- Lưu trước khi sang ảnh tiếp theo.

Zoom từ 200% trở lên cho vùng đầu, vì khoảng cách hai mắt trong bộ này có lúc chỉ 9 px.

Sau khi làm xong 2 ảnh đầu, đối chiếu với phần A để thống nhất cách đặt điểm giữa hai nửa dataset.

### 5.5. Thứ tự đặt điểm trong một ảnh

Dùng chung cho cả phần A và phần B:

- Kiểm tra trái/phải theo khung hình: R ở bên phải ảnh, L ở bên trái ảnh.

- Chỉ ở phần A: xử lý các điểm ở góc (0, 0), quyết định từng điểm theo mục 4.1. Đây là phần nặng nhất nên làm sớm.

- Đặt thân mình: hai vai và hai hông. Bốn điểm này định khung cho phần còn lại.

- Đặt chi trên: khuỷu và cổ tay.

- Đặt vùng đầu: mũi, mắt, tai.

- Đặt chi dưới, làm cuối cùng khi đã có khung thân.

- Đặt trạng thái cho cả 17 điểm.

- Lưu trước khi sang ảnh tiếp theo.

## 6. Tình huống đặc biệt

### 6.1. Keypoint ở toạ độ (0, 0)

Xuất hiện ở 274 trên 400 ảnh, tổng 455 điểm, phân bố như sau:

| Keypoint | Số lần | Keypoint | Số lần |
|---|---|---|---|
| Point 4 – R Ear | 220 | Point 14 – R Knee | 13 |
| Point 16 – R Ankle | 118 | Point 15 – L Knee | 11 |
| Point 17 – L Ankle | 82 | các điểm còn lại | 11 |

Toạ độ hiện tại không mang thông tin nên không kéo nhẹ cho gần đúng. Nhìn ảnh, tự xác định khớp đó ở đâu, rồi áp quy tắc ở mục 4.1: thấy được thì kéo về đúng vị trí và đánh Visible, không thấy nhưng suy ra được thì kéo về vị trí ước lượng và đánh Occluded, còn lại thì Outside.

Nếu sau khi nộp vẫn còn điểm nằm trong vùng 50 px từ góc trên-trái trong khi người lái ở giữa khung, job sẽ bị trả lại.

### 6.2. Hai keypoint chồng lên nhau

Có 9 cặp điểm cách nhau dưới 3 px mà cả hai đều khác trạng thái Outside, trong đó 3 cặp cả hai đều Visible. Ví dụ đã gặp là điểm tai nằm đè lên nose.

Hai khớp khác nhau không thể trùng toạ độ khi cả hai đều Visible. Tách ra đúng vị trí, hoặc đánh lại trạng thái cho điểm không thực sự nhìn thấy.

### 6.3. Điểm chi dưới rơi vào đồ vật

Mô hình hay đặt điểm lên vật có hình dạng gần giống chi như ghế, cần số, bảng táp-lô. Kiểm tra từng điểm gối và cổ chân xem có nằm trên cơ thể người không. Nằm trên đồ vật là luôn sai: kéo về cơ thể nếu thấy chi, còn không thì Outside.

Đây là lỗi dễ bỏ sót vì skeleton nhìn tổng thể vẫn có vẻ hợp lý.

### 6.4. Chi dưới khuất hoàn toàn

Xảy ra thường xuyên vì đặc thù ảnh chụp trong cabin. Xử lý theo bảng ở mục 3.3.

### 6.5. Khung hình xoay 90°

Ảnh bị xoay 90° không làm thay đổi quy ước Left/Right: trái ảnh vẫn là L, phải ảnh vẫn là R. Chỉ hướng đầu–chân của cơ thể bị xoay; không xoay lại quy ước trái/phải theo cơ thể.

### 6.6. Người lái vặn mình hoặc quay lưng

Khi người lái vặn mình hoặc quay lưng, KHÔNG đảo quy ước trái/phải theo giải phẫu. Điểm nào nằm phía phải khung hình vẫn thuộc nhóm R; điểm nào nằm phía trái khung hình vẫn thuộc nhóm L.

Kiểm tra chéo bằng topology và vị trí trên ảnh: chuỗi vai–khuỷu–cổ tay ở mỗi phía phải tạo thành một chi liên tục, đồng thời nhóm R/L phải nằm đúng phía khung hình theo quy ước VF.

### 6.7. Người thứ hai trong khung

Một số ảnh có hành khách hoặc người ở ghế sau lọt vào. Mặc định chỉ gán nhãn người lái. Pre-label chỉ chứa một skeleton mỗi ảnh, nên mọi skeleton thứ hai đều do mentor quyết định. Nếu không xác định được ai là người lái, mở Issue.

### 6.8. Thiếu sáng hoặc nhoè

Đặt điểm ở vị trí tốt nhất ước lượng được và đánh Occluded nếu ranh giới không rõ. Nếu tối đến mức không phân biệt được người với ghế, mở Issue.

### 6.9. Pre-label lệch toàn bộ

Dấu hiệu là cả 17 điểm giữ đúng hình dạng skeleton nhưng dịch đều sang một phía. Đây là lỗi hệ thống do sai scale hoặc sai mapping frame, không phải lỗi từng điểm. Báo mentor thay vì sửa tay cả 40 ảnh.

### 6.10. Pre-label đã đúng

Giữ nguyên vị trí nhưng vẫn rà lại trạng thái từng điểm. Giữ nguyên là một kết quả hợp lệ.

## 7. Tự kiểm tra trước khi nộp

### 7.1. Từng frame

- Đúng một skeleton cho người lái, trừ khi mentor yêu cầu khác.

- Đủ 17 keypoint, mỗi điểm có trạng thái rõ ràng.

- Không còn điểm nào ở góc (0, 0) hoặc sát góc trên-trái.

- Trái/phải đúng theo khung hình VinFast: R ở bên phải ảnh, L ở bên trái ảnh.

- Mỗi cánh tay và mỗi chân tạo thành chuỗi liền mạch, không bắt chéo sang bên kia thân.

- Không có hai điểm khác nhau trùng toạ độ khi cả hai đều Visible.

- Không có điểm nào nằm trên ghế, vô-lăng, cần số hay bảng táp-lô.

- Điểm Occluded có toạ độ ước lượng hợp lý.

- Điểm Outside đúng là ngoài khung hoặc không suy ra được.

### 7.2. Cả job

- Đã làm đủ 60 ảnh.

- Đã đối chiếu schema ở phần B: đúng 1 label và 17 sublabel, tên trùng khít với phần A.

- Đã rà lại ít nhất 10 frame, trong đó có 1 frame chi dưới khuất, 1 frame người vặn mình, 1 frame thiếu sáng, 1 frame pre-label có nhiều điểm ở (0, 0).

- Mọi trường hợp không chắc đã mở Issue thay vì tự đặt luật mới.

## 8. Sai số cho phép

Kích thước tham chiếu đo trên bộ ảnh: vai đến vai trung vị 132 px, vai đến hông 259 px.

| Nhóm điểm | Ngưỡng |
|---|---|
| Khớp lớn nhìn rõ: vai, hông, gối | 8 px |
| Khớp nhỏ nhìn rõ: khuỷu, cổ tay, cổ chân | 10 px |
| Vùng đầu: mũi, mắt, tai | 6 px |
| Điểm Occluded | 20 px |
| OKS so với nhãn chuẩn | từ 0,85 trở lên |

Các ngưỡng này là đề xuất khởi điểm, sẽ được chốt lại sau khi mentor hoàn thành bộ ảnh chuẩn.

## 9. Lỗi thường gặp

| Lỗi | Nguyên nhân | Xử lý |
|---|---|---|
| Đảo trái phải toàn bộ job | Dùng quy ước giải phẫu/COCO thay vì quy ước VF theo khung hình | R phải ở bên phải ảnh, L ở bên trái ảnh; xem mục 2.1 |
| Kéo điểm (0, 0) cho gần đúng | Tưởng toạ độ có ý nghĩa | Toạ độ không mang thông tin, quyết định lại từ đầu, xem mục 6.1 |
| Đặt gối hoặc cổ chân lên ghế, cần số | Cần chỗ để đặt điểm | Không thấy thì Outside, xem mục 6.3 |
| Đặt cổ tay lên vành vô-lăng | Vô-lăng dễ nhìn hơn cổ tay | Cổ tay ở nếp gấp cổ tay, xem mục 3.2 |
| Đặt hông ở cạp quần | Nhầm mốc giải phẫu | Hông là tâm khớp háng, xem mục 3.3 |
| Đặt tai ở chóp vành tai | Nhầm mốc giải phẫu | Tai là ống tai, xem mục 3.1 |
| Nhầm trên dưới của cơ thể | Khung hình xoay 90° | Xác định đầu–chân theo trục cơ thể, nhưng Left/Right vẫn theo khung hình; xem mục 6.5 |
| Dùng Hidden thay Outside | Nhầm chức năng CVAT | Hidden chỉ ẩn hiển thị, xem mục 4 |
| Gán nhãn cả hành khách | Không có luật | Chỉ gán người lái, xem mục 6.7 |
| Sửa tay 40 ảnh bị lệch hệ thống | Không nhận ra lỗi hệ thống | Báo mentor, xem mục 6.9 |
| Schema phần B đặt node R/L sai phía khung vẽ | Dùng thói quen giải phẫu hoặc COCO | R ở nửa phải, L ở nửa trái khung vẽ; xem mục 5.3 |
| Hai người cùng sửa Labels, schema bị ghi đè | Không phân công ai dựng | Một người dựng, cả nhóm kiểm tra, xem mục 5.3 |

## 10. Phụ lục — schema đối chiếu

Dùng để kiểm tra lại schema tự dựng ở mục 5.3. Chỉ dán thẳng vào tab Raw khi mentor cho phép.

File: schema/VF_HumanPose17_CVAT_Raw_Label_numeric_1_to_17_CORRECTED.json

Cấu trúc rút gọn, phần svg lược bớt cho dễ đọc:

[
  {
    "name": "person",
    "type": "skeleton",
    "attributes": [],
    "sublabels": [
      { "name": "1",  "type": "points", "attributes": [] },
      { "name": "2",  "type": "points", "attributes": [] },
      { "name": "3",  "type": "points", "attributes": [] },
      { "name": "4",  "type": "points", "attributes": [] },
      { "name": "5",  "type": "points", "attributes": [] },
      { "name": "6",  "type": "points", "attributes": [] },
      { "name": "7",  "type": "points", "attributes": [] },
      { "name": "8",  "type": "points", "attributes": [] },
      { "name": "9",  "type": "points", "attributes": [] },
      { "name": "10", "type": "points", "attributes": [] },
      { "name": "11", "type": "points", "attributes": [] },
      { "name": "12", "type": "points", "attributes": [] },
      { "name": "13", "type": "points", "attributes": [] },
      { "name": "14", "type": "points", "attributes": [] },
      { "name": "15", "type": "points", "attributes": [] },
      { "name": "16", "type": "points", "attributes": [] },
      { "name": "17", "type": "points", "attributes": [] }
    ],
    "svg": "<line ... data-node-from=\"1\" data-node-to=\"2\"></line> ... <circle ... data-node-id=\"1\" data-label-name=\"1\"></circle> ..."
  }
]

Ba quy tắc rút ra từ schema, dùng để tự kiểm tra:

- data-label-name của mỗi circle phải trùng đúng số của một sublabel; thứ tự các circle trùng thứ tự sublabel, tức node 1 là Nose và node 17 là L Ankle theo bảng VF ở mục 2.2.

- data-node-id chạy liên tục từ 1 đến 17.

- data-node-from và data-node-to của mỗi line chỉ nhận giá trị từ 1 đến 17.
