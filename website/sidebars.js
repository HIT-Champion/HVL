// Copyright 2026 Signet Team
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// SPDX-License-Identifier: Apache-2.0

// Mục lục bên trái. Mã trang là đường dẫn tệp tính từ gốc repo, bỏ đuôi .md. Tên trang trên mục lục đặt ở đây để tệp
// .md không cần front matter (GitHub hiện front matter thành bảng ở đầu tệp). Thêm trang mới trong docs/ thì thêm một
// dòng vào đúng nhóm; trang không có trong mục lục vẫn được dựng và tìm được.

const trang = (id, label) => ({type: 'doc', id, label});

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
export default {
  taiLieu: [
    trang('docs/README', 'Xem nhanh 5 phút'),
    trang('README', 'Giới thiệu Signet'),
    {
      type: 'category',
      label: 'Hướng dẫn sử dụng',
      link: {type: 'doc', id: 'docs/huong-dan/README'},
      items: [
        trang('docs/huong-dan/van-thu', 'Văn thư'),
        trang('docs/huong-dan/chuyen-vien', 'Chuyên viên'),
        trang('docs/huong-dan/lanh-dao-phong', 'Lãnh đạo phòng'),
        trang('docs/huong-dan/lanh-dao-don-vi', 'Lãnh đạo đơn vị'),
        trang('docs/huong-dan/quan-tri', 'Quản trị đơn vị'),
        trang('docs/huong-dan/viec-chung', 'Việc chung của mọi vai trò'),
      ],
    },
    trang('docs/thuat-ngu', 'Thuật ngữ'),
    {
      type: 'category',
      label: 'Dự thi OLP PMNM 2026',
      link: {type: 'doc', id: 'docs/du-thi/README'},
      items: [
        trang('docs/du-thi/pof-checklist', 'Bảng tự chấm PoF'),
        trang('docs/du-thi/hoi-dap-hoi-dong', 'Hỏi đáp với hội đồng'),
        trang('docs/du-thi/ke-hoach-phat-trien', 'Kế hoạch phát triển'),
        trang('docs/du-thi/olp-2026-de-thi', 'Phân tích đề thi'),
        trang('docs/du-thi/olp-2026-brief', 'Thể lệ và thang điểm'),
      ],
    },
    {
      type: 'category',
      label: 'Sản phẩm',
      items: [
        trang('docs/dac-ta-san-pham', 'Đặc tả sản phẩm'),
        trang('docs/muc-hoan-thien', 'Mức hoàn thiện'),
        trang('docs/demo-script', 'Kịch bản demo'),
        trang('docs/danh-gia-ai', 'Đánh giá AI'),
        trang('docs/so-lieu-sau', 'Số đo và góp ý'),
        trang('docs/tu-chan-doan', 'Tự chẩn đoán H-P-D-I'),
        trang('ROADMAP', 'Lộ trình'),
      ],
    },
    {
      type: 'category',
      label: 'Cài đặt và vận hành',
      items: [
        trang('docs/trien-khai', 'Triển khai, nâng cấp'),
        trang('docs/van-hanh', 'Vận hành'),
        trang('SECURITY', 'Chính sách bảo mật'),
      ],
    },
    {
      type: 'category',
      label: 'Nhà phát triển',
      items: [
        trang('docs/architecture', 'Kiến trúc'),
        trang('docs/mo-hinh-du-lieu', 'Mô hình dữ liệu'),
        {
          type: 'category',
          label: 'API',
          link: {type: 'doc', id: 'docs/api/README'},
          items: [trang('docs/api/thao-tac-theo-vai-tro', 'Thao tác theo vai trò')],
        },
        trang('docs/them-ung-dung', 'Thêm ứng dụng mới'),
        {
          type: 'category',
          label: 'Thành phần trong kho',
          items: [
            trang('services/svc-files/README', 'svc-files'),
            trang('services/svc-workflow/README', 'svc-workflow'),
            trang('db/README', 'db — CSDL, Hasura'),
            trang('schemas/README', 'schemas — JSON Schema'),
            trang('platform/README', 'platform'),
            trang('platform/apisix/README', 'APISIX'),
            trang('platform/keycloak/README', 'Keycloak'),
            trang('apps/office/README', 'app-office'),
            trang('apps/ca-nhan/README', 'app-ca-nhan'),
            trang('apps/bang-tin/README', 'app-bang-tin'),
            trang('apps/nghi-phep/README', 'app-nghi-phep'),
          ],
        },
        trang('CONTRIBUTING', 'Hướng dẫn đóng góp'),
        trang('docs/git_flow', 'Quy trình Git'),
        trang('DEPENDENCIES', 'Phụ thuộc và giấy phép'),
        trang('CODE_OF_CONDUCT', 'Quy tắc ứng xử'),
      ],
    },
    trang('CHANGELOG', 'Lịch sử thay đổi'),
    trang('README.en', 'English overview'),
  ],
};
