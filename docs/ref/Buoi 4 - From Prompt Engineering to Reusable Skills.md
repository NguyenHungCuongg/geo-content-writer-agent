# Buổi 04 – From Prompt Engineering to Reusable Skills

*MSc. Ngô Ngọc Đăng Khoa*

## Agenda

1. Từ chatbot đến agent
2. Agent Skill
3. Thiết kế skill
4. Phương pháp tạo skill trong thực tế (in real-world)
5. Agent-native software và tricks

---

## 1. Từ chatbot đến agent

### AI đã tiến hoá

> Chatbot trả lời câu hỏi. Agent hoàn thành nhiệm vụ.

- **Chatbot:** người dùng gõ câu hỏi, nhận text, copy ra ngoài tự xử lý tiếp.
- **Agent:** nhận nhiệm vụ, lên kế hoạch, gọi công cụ, thực thi từng bước, kiểm tra kết quả.
  - Khả năng: đọc/ghi file, chạy code, gọi API, tự điều chỉnh và lặp lại khi gặp lỗi.
  - Người dùng mô tả kết quả mong muốn; agent tự xử lý.

**Ví dụ:** tạo ảnh avatar bằng cách crop khuôn mặt trong ảnh đính kèm và resize theo kích thước chuẩn của avatar Facebook. Có thể thực hiện trên Claude Chat hoặc trên IDE agent (Antigravity).

### Phân loại: cloud agent và local agent

**Cloud agent** vận hành trong sandbox của nhà cung cấp, có nhiều giới hạn.
- Ứng dụng web-based. Khả năng: chạy code, đọc/ghi file, cài tool/thư viện trong sandbox.
- Giới hạn: người dùng phải upload file lên cho agent xử lý, và download kết quả khi xong.
- Công cụ tiêu biểu: Claude Chat, ChatGPT Chat, Gemini.
- Ví dụ: Claude Chat transcribe một clip YouTube.

**Local agent** vận hành trực tiếp trên máy tính cá nhân.
- Cài trên máy, chạy trên terminal hoặc IDE, có toàn quyền trên hệ thống file.
- Khả năng: đọc/ghi bất kỳ file nào, chạy lệnh hệ thống, kết nối mạng nội bộ, tự động hoá theo lịch, sử dụng các công cụ được thiết lập trên máy.
- Công cụ tiêu biểu: Claude Code, Claude Cowork, ChatGPT Work, Codex, Antigravity IDE/CLI, OpenClaw, Hermes.
- Ví dụ: Claude Code transcribe clip YouTube; OpenCode tổ chức và cập nhật link ảnh cho slide.

**So sánh Cloud và Local agent:**

| Tiêu chí | Cloud agent | Local agent |
|---|---|---|
| Vận hành | Sandbox của nhà cung cấp | Máy cá nhân |
| Khởi động | Trình duyệt | Cần cài đặt |
| File | Upload & download | Đọc/ghi trực tiếp |
| Lệnh & CLI | Chỉ thứ sandbox cho phép | Tự do |
| Mạng nội bộ | Bị chặn | Truy cập được |

### Vì sao local agent làm được nhiều việc hơn

Local agent không bị giới hạn nên thực hiện được nhiều loại task hơn. Model LLM thông minh hơn sẽ thực hiện được nhiều loại task hơn, với cách xử lý chuẩn hơn.

**Ví dụ thực nghiệm** – tác vụ dịch Anh–Việt giữ định dạng docx (75 sections):

| Model | Kết quả | Tool call | Token |
|---|---|---|---|
| Haiku 4.5 | 68/75 sections, sót header, footer, footnote | 15 | 216.339 |
| Opus 4.8 | 75/75 sections | 88 | 2.226.979 |

- Haiku 4.5: 15 tool call, cố gắng giải quyết một lúc rồi bỏ cuộc, giao 68/75 sections mà không báo là còn thiếu.
- Opus 4.8: 88 tool call, quyết tâm đến cùng, dịch đủ 75/75 sections nhưng tốn đến 2,2 triệu token.
- **Kết luận:** Haiku làm sót; Opus làm đúng nhưng burn token nhiều gấp khoảng 32 lần.

**Ví dụ tóm tắt clip YouTube:** có tác vụ đơn giản (chỉ cần 2 bước: lấy subtitle/transcribe → tóm tắt) nhưng agent xử lý cồng kềnh, hoặc chọn sai phương pháp; một số model giá rẻ thậm chí thất bại.

**Câu hỏi đặt ra:** lần chạy kế tiếp, người dùng có ép agent chạy theo phương pháp đã đúng lần này, và tái sử dụng các script của lần này được không?

### Làm lại với một ít hướng dẫn

Thêm một ít hướng dẫn cho agent, rồi chạy lại:

| Model | Kết quả | Tool call | Token |
|---|---|---|---|
| Haiku 4.5 | 75/75 sections | 10 | 73.288 |
| Opus 4.8 | 75/75 sections | 8 | 68.892 |

- Hướng dẫn agent dùng model giá rẻ xử lý được task tiệm cận model cao cấp.
- Ép agent mọi run đều cho kết quả tương đương nhau, đảm bảo workflow và tái sử dụng được các script.

---

## 2. Agent Skill

### Hướng dẫn đặt ở đâu?

**Cách đơn giản nhất: chèn vào prompt** (prompt engineering).
- Dễ quên hoặc sót chi tiết.
- Chỉ phù hợp với hướng dẫn cho tác vụ đơn giản.
- Agent bị động.

**Cơ chế khác: skill.**
- **Prompt:** mỗi lần dùng là một lần gõ lại, giải thích lại từ đầu.
- **Skill:** thiết lập một lần, agent dùng lại, sẵn sàng chia sẻ cho người khác.
- Người tạo skill chuyển kinh nghiệm cá nhân thành năng lực dùng chung.
- Skill giúp agent xử lý một loại nhiệm vụ.

Ví dụ skill: `summarize-yt` (tóm tắt clip YouTube), `group-images-by-faces` (nhóm ảnh theo khuôn mặt).

### Định nghĩa Skill

> Skill là tập hợp hướng dẫn và công cụ được chuẩn bị sẵn, giúp agent hoàn thành một loại công việc cụ thể một cách nhất quán.

- **Không có skill:** agent tự xoay sở, kết quả không nhất quán.
- **Có skill:** agent đọc hướng dẫn, dùng công cụ có sẵn, tuân thủ quy trình, kết quả nhất quán.
- Giảm số lần thử và sai, tiết kiệm token và chi phí.
- Skill được lưu dưới dạng file: dễ đọc, chỉnh sửa và chia sẻ.

### Cấu trúc thư mục skill

```
my-skill/
├── SKILL.md        # Hướng dẫn tổng quan: skill này làm gì, khi nào kích hoạt
├── references/     # Tài liệu chi tiết: quy trình từng bước, quy tắc định dạng, ví dụ mẫu
├── examples/       # Ví dụ minh hoạ; tham chiếu khi làm rõ hành vi mong muốn
└── scripts/        # Đoạn code nhỏ hỗ trợ: xử lý file, gọi API, convert định dạng
```

Agent đọc các file này như đọc tài liệu hướng dẫn, rồi thực thi.

### SKILL.md

- **Frontmatter YAML** cấu hình skill:
  - `name`: tên skill; slash command để người dùng gọi trực tiếp `/tên-skill`.
  - `description`: agent dùng để quyết định khi nào kích hoạt skill.
  - Các mục khác: `allowed-tools`, `hooks`, ... (phụ thuộc vào agent harness).
- Hướng dẫn thực thi được viết dưới dạng markdown.

---

## 3. Thiết kế skill

### Trigger

Frontmatter `description` là phần **duy nhất** agent luôn đọc, kể cả khi chưa load skill.

Ví dụ: "Tạo study guide từ bài viết, lecture note hoặc paper khi người dùng cần tóm tắt, glossary, quiz. Không dùng để dịch hoặc chỉnh định dạng."

### Workflow

`SKILL.md` là bản đồ hướng dẫn cho agent thực hiện nhiệm vụ.

**Nguyên tắc:**
- Mô tả thứ tự thực hiện, khoảng 5–8 bước.
- Mỗi bước một dòng, động từ đứng đầu.
- Trỏ tới file chi tiết, không copy nội dung.
- Bước cuối phải là kiểm tra.

**Ví dụ: skill `study-guide`**
1. Kiểm tra input hợp lệ.
2. Đọc và phân tích tài liệu.
3. Rút ra các khái niệm chính.
4. Đọc `references/output-format.md`.
5. Sinh study pack theo format đó.
6. Chạy `scripts/check_pack.py`.
7. Chỉ trả kết quả khi bước 6 đạt.

**Progressive disclosure:** agent không cần mọi thứ ngay từ đầu. SKILL cần hướng dẫn agent cách nạp thông tin.

### Context

- `SKILL.md` phình to là dấu hiệu skill cần được chia nhỏ.
- Giữ `SKILL.md` gọn, thường dưới 200 dòng; chi tiết đẩy sang `references/`.

### Output

- Nêu rõ định dạng (markdown, docx, json), nơi lưu, quy ước đặt tên file.
- Liệt kê các phần bắt buộc phải có trong kết quả.
- Kèm một file mẫu trong `examples/`.
- Với dữ liệu có cấu trúc như json, csv, hãy đưa schema vào.
- Mô tả output chính là viết sẵn tiêu chí cho giai đoạn verification.

### Machine vs LLM

Phải xác định rõ: nhiệm vụ này cần **suy luận** hay cần **chính xác**?

- **`references/` → LLM:** quy tắc nghiệp vụ, tiêu chí chất lượng, định dạng đầu ra, checklist chuyên sâu, việc cần cân nhắc, đánh giá, diễn đạt.
- **`scripts/` → machine:** đếm đủ 10 câu quiz chưa, kiểm tra các section bắt buộc, phân tích cấu trúc docx, validate JSON, convert định dạng, render để kiểm tra.

### Verification

- Kết quả thế nào là hợp lệ? Phần nào bắt buộc phải có?
- Có cần chạy test, render file, hay đối chiếu checklist không?
- Nếu kiểm tra thất bại, agent phải sửa rồi kiểm lại, không được trả kết quả.
- Viết thẳng vào workflow: "chỉ tuyên bố hoàn thành khi bước kiểm tra trả về PASSED".
- Yêu cầu agent không tuyên bố hoàn thành trước khi có bằng chứng.

### Ví dụ skill hoàn chỉnh: `summarize-yt`

```yaml
---
name: summarize-yt
description: Tóm tắt clip YouTube thành ghi chú tiếng Việt. Dùng khi người dùng đưa link YouTube và cần transcript, tóm tắt hoặc ghi chú bài giảng.
allowed-tools: Bash(yt-dlp *), Bash(python3 *), Read, Write
---

## Workflow
1. Kiểm tra input là URL YouTube hợp lệ.
2. Lấy phụ đề có sẵn: `scripts/fetch_subtitle.sh <url>`.
3. Nếu không có phụ đề, transcribe local: `scripts/transcribe.py <url>`.
4. Đọc `references/note-format.md`, viết ghi chú đúng cấu trúc đó.
5. Chạy `scripts/check_note.py` để kiểm tra các mục bắt buộc.
6. Chỉ báo hoàn thành khi bước 5 trả về PASS.
```

### Skill cũng cần được kiểm thử

| Loại kiểm thử | Câu hỏi cần trả lời |
|---|---|
| Trigger | Có kích hoạt đúng skill khi cần không? |
| False-trigger | Có kích hoạt nhầm khi việc không liên quan không? |
| Functional | Có chạy đủ các bước, kể cả trường hợp đặc thù và input lỗi? |
| Quality | Kết quả có tốt hơn khi không dùng skill không? |
| Efficiency | Có giảm token, tool call, thời gian không? |
| Safety | Có đòi quyền hoặc tool vượt quá nhu cầu không? |

### Năm lỗi thường gặp

1. **SKILL.md khổng lồ.**
2. **Description mơ hồ** khiến skill được kích hoạt không như mong đợi.
3. **Một skill xử lý nhiều nhiệm vụ:** khó verify và điều chỉnh.
4. **Yêu cầu LLM làm việc của machine** (đếm, validate, convert): dễ sai và tốn token.
5. **Thiếu bước kiểm tra.**

---

## 4. Phương pháp tạo skill trong thực tế

**Quy trình:**
1. Chọn một nhiệm vụ agent làm chưa tốt; làm cùng agent tới khi đạt.
2. Ghi lại cách làm đã thành công: thứ tự các bước, câu lệnh, quy tắc.
3. Đóng gói thành skill: `SKILL.md` + `references/` + `scripts/`.
4. Chạy lại trên nhiều trường hợp khác nhau, bổ sung những điều skill còn sót.
5. Quản lý như mã nguồn: commit, ghi lý do thay đổi, cần thì revert.

> Skill thường được "thai nghén" từ một lần agent không hoàn thành tốt nhiệm vụ.

### Hãy để agent viết skill giúp bạn

- Bạn không cần viết skill từ con số không.
- Các agent (Claude Code, Codex, Hermes, ...) đều có sẵn skill `skill-creator`: mô tả nhu cầu, agent dựng cấu trúc thư mục, `SKILL.md` và script mẫu.
- Cung cấp phiên chat: "dựa trên các lỗi trong phiên này, tạo (hoặc cải thiện) skill ..."
- **Bắt buộc đọc lại** những gì agent viết. Bạn là người chịu trách nhiệm về skill được tạo ra.

---

## 5. Tricks

### Tự động đề xuất tạo skill

Đoạn ví dụ đặt trong `CLAUDE.md` / `AGENTS.md`:

> You are not allowed to do one-off work. If I ask you to do something and it's the kind of thing that will need to happen again, you must:
> 1. Do it manually the first time (3–10 items).
> 2. Show me the output and ask if I like it.
> 3. If I approve, codify it into a `SKILL.md` file in `workspace/skills/`.
> 4. If it should run automatically, add it to cron.

### Tự động đề xuất tạo skill (tiếp)

> Every skill must be MECE: each type of work has exactly one owner skill. No overlap, no gaps. Before creating a new skill, check if an existing one already covers it. If so, extend it instead.
>
> The test: if I have to ask you for something twice, you failed. The first time I ask is discovery. The second time means you should have already turned it into a skill running on a cron.
>
> When building a skill, follow this cycle: **Concept → Prototype → Evaluate → Codify → Cron → Monitor.**
>
> Every conversation where I say "can you do X" should end with X being a skill on a cron, not a memory of "he asked me to do X that one time."
>
> The system compounds. Build it once, it runs forever.
