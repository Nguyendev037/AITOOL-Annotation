<!-- GENERATED from guildlline/Semantic_Segmentation_Annotation_Guideline.pdf (sha256 8d8d1dc910b2a136799e9d94469d4bbc7f8e59bf4c036f0835add38a5ca2698d, engine pdfplumber) -->

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
