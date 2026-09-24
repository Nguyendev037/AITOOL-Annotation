# Kế hoạch nâng cấp CVAT Browser Agent

## Mục tiêu

Nâng cấp dự án thành hệ thống gán nhãn có nhiều model theo từng bài toán, cho phép bật/tắt từng model, đồng bộ guideline PDF/DOCX thành YAML ánh xạ label, giữ luồng tương tác CVAT qua browser-agent, và chuẩn bị quy trình train dễ dùng. Bản LiDAR đầu tiên đọc PCD và tự fit cuboid 3D từ vùng điểm do người dùng chọn.

Giữ nguyên và rà soát các thay đổi đang có trong working tree. Không chạy huấn luyện hoặc tạo checkpoint mới trong đợt nâng cấp này.

## 1. Quản lý model và suy luận

- Tạo `models.yaml` làm registry. Mỗi model khai báo `id`, bài toán, loại annotation đầu ra, backend, đường dẫn checkpoint, tập label, trạng thái `enabled` và cờ `default`.
- Đăng ký các nhánh hiện có: BBox, semantic, drivable, lane, pose17 và face50; chừa hợp đồng cho model LiDAR 3D bổ sung sau. Cho phép nhiều model cùng bài toán bật đồng thời. Lệnh chạy chọn model theo ID, hoặc dùng model mặc định của bài toán.
- Tạo CLI `python tools/models.py list|enable|disable|check|sync-cvat`. `sync-cvat` chỉ quản lý những function thuộc dự án: triển khai model đang bật, gỡ function của model đã tắt để nó không còn hiện trong trang Models của CVAT localhost. Endpoint suy luận cũng từ chối model đã tắt.
- Giữ các endpoint hiện có để không làm hỏng client và Nuclio adapter cũ. Bổ sung cách chọn model theo ID trong hợp đồng suy luận chung; nạp model khi cần và giới hạn suy luận GPU để phù hợp RTX 4060 8 GB.
- Rà soát mã nguồn đang hoạt động, nhánh cũ và tài liệu trùng hoặc mâu thuẫn; hợp nhất cấu hình, đường chạy và thông báo lỗi mà không xóa dữ liệu hoặc thay đổi ngoài phạm vi dự án.

## 2. Đồng bộ guideline và ánh xạ label

- Dùng `guildlline/` làm nơi giữ PDF/DOCX gốc. Hợp nhất hai luồng sync hiện tại: trích xuất tài liệu cục bộ, lưu hash và Markdown để có thể chạy offline, sau đó gọi DeepSeek khi tài liệu đổi và có API key.
- DeepSeek sinh YAML theo từng bài toán trong `guideline/profiles/`. Mỗi mục ghi label trong tài liệu, label của model tương ứng, loại shape, mức hỗ trợ và vị trí dẫn chứng trong nguồn. Với một tài liệu bao gồm nhiều bài toán, tạo nhiều profile.
- Kiểm tra YAML trước khi áp dụng: schema hợp lệ, không trùng/xung đột ánh xạ, label đích có trong model, shape tương thích, dẫn chứng tồn tại và không làm đổi label ID đang dùng trong CVAT. Profile đạt kiểm tra tự có hiệu lực; profile mơ hồ hoặc không được model hỗ trợ được giữ ở trạng thái chờ và báo lý do. Không tự ghi đè `taxonomy.yaml` từ văn bản tự do.
- Cho phép đối chiếu profile với label của một CVAT task local trước khi auto-annotation. Cập nhật `sync_all.py --status`, `--check` và chế độ offline; đặc biệt sửa `--check` để tuyệt đối không ghi file khi phát hiện lệch.
- Giữ DeepSeek là mặc định, nhưng tách cấu hình nhà cung cấp LLM để sau này đổi model mà không sửa logic đồng bộ.

## 3. Browser-agent và LiDAR 3D

- Nối browser-use với registry model và profile guideline trong một lệnh chạy theo task. Giữ chế độ xem trước, kiểm tra label/rule và báo lỗi rõ ràng trước khi ghi annotation. Kiểm tra lại luồng pose17/face50 đang dùng model có sẵn và các tài liệu hướng dẫn liên quan.
- LiDAR v1 đọc file PCD, nhận vùng chọn bằng sáu giới hạn `xmin ymin zmin xmax ymax zmax`, lọc điểm nhiễu, chọn cụm trong vùng và fit cuboid 3D. Kết quả gồm tọa độ, kích thước, góc quay và thống kê số điểm; không tự nhận diện lớp vật thể.
- Xuất preview HTML để kiểm tra cuboid trên point cloud và gói annotation Datumaro 3D để người dùng import vào task CVAT localhost sau khi xem trước. Kiểm tra khứ hồi export/import trên task 3D mẫu trước khi coi chức năng hoàn thành. CVAT hỗ trợ task point cloud và cuboid; serializer phải được kiểm chứng với phiên bản local thực tế: [tài liệu task 3D](https://docs.cvat.ai/docs/workspace/tasks-page/), [tài liệu Datumaro](https://docs.cvat.ai/docs/dataset_management/formats/format-datumaro/).
- Detector 3D tự tìm vật thể sẽ tích hợp sau khi có dữ liệu 3D thực tế. Bản này không đưa một model 3D pretrained chưa kiểm chứng vào luồng gắn nhãn chính.

## 4. Chuẩn bị train và viết lại hướng dẫn

- Tạo một CLI thống nhất: `python tools/train.py --task <bài_toán> --dataset <thư_mục> --check` để kiểm tra dữ liệu, và cùng lệnh với `--train` để huấn luyện khi người dùng chủ động chạy. Hỗ trợ các bài BBox, semantic, pose17, face50 và LiDAR 3D; mỗi bài có đầu vào, bộ chuyển đổi, cấu hình model, đánh giá và manifest checkpoint riêng.
- BBox và semantic nhận dữ liệu YOLO đang dùng trong repo. Pose17 và face50 nhận dữ liệu keypoint với đúng thứ tự 17/50 điểm, chuyển sang định dạng YOLO pose. LiDAR nhận PCD cùng cuboid 3D đã gán nhãn và chuyển sang định dạng dữ liệu của PointPillars. Các bộ chuyển đổi phải báo rõ ảnh/point cloud thiếu nhãn, class ID sai, keypoint thiếu, tọa độ sai và split không hợp lệ. Tham khảo [định dạng pose Ultralytics](https://docs.ultralytics.com/datasets/pose) và [custom dataset OpenPCDet](https://github.com/open-mmlab/OpenPCDet/blob/master/docs/CUSTOM_DATASET_TUTORIAL.md).
- Chia train/validation theo scene hoặc sequence để tránh rò rỉ frame liền kề. Báo thống kê số mẫu và class trước khi train; chỉ cho phép chia ngẫu nhiên trên dữ liệu quá nhỏ khi người dùng chọn chế độ demo rõ ràng. Không tự bật checkpoint mới sau train; người dùng đăng ký nó vào registry rồi bật bằng CLI quản lý model.
- Viết lại `README.md`, `docs/USAGE.md` và `docs/TRAINING.md` thành quy trình PowerShell ngắn: chuẩn bị môi trường, kiểm tra dữ liệu, chạy từng bài toán, xem kết quả, dùng trong CVAT và xử lý lỗi. Mỗi bước có lệnh `python` nổi bật, sao chép chạy được, kèm đầu vào và đầu ra dự kiến. Xóa hoặc sửa các lệnh, đường dẫn và mô tả kiến trúc đã lỗi thời.

## Kiểm thử và điều kiện hoàn thành

- Giữ 79 test hiện đang qua. Thêm test cho registry và bật/tắt model; sync có/không có API key; YAML hợp lệ, thiếu label và xung đột; bảo đảm `--check` không ghi file; chuyển đổi dữ liệu train; fit cuboid từ PCD mẫu và gói import.
- Chạy `--check`/fixture cho cả năm bài train, nhưng không chạy huấn luyện thật. Hai dataset BBox/semantic hiện có đều chỉ 25 ảnh, nên dùng để kiểm tra luồng chứ không làm bằng chứng chất lượng model.
- Khi Docker Desktop hoạt động, kiểm tra health và suy luận của model-service, bật/tắt model trong CVAT localhost, browser-use ở chế độ xem trước, và import cuboid vào task 3D mẫu. Tại thời điểm lập kế hoạch, Docker daemon chưa chạy; phần tích hợp này chưa được xác minh.

## Các quyết định đã chốt

- Đích đầu tiên là CVAT localhost.
- Nhiều model cùng bài toán có thể bật đồng thời; mỗi bài có một model mặc định.
- YAML guideline hợp lệ được tự áp dụng; trường hợp mơ hồ phải được báo và giữ chờ.
- LiDAR v1 dùng PCD, chọn vùng 3D bằng tọa độ, auto-fit cuboid, xem preview rồi import file; detector 3D triển khai sau.
- Dữ liệu train pose, face và LiDAR sẽ bổ sung sau. Đợt này chuẩn bị lệnh và bộ kiểm tra để khi có dữ liệu có thể dùng ngay, nhưng không chạy train.
