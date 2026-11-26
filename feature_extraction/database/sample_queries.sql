-- Truy vấn mẫu để kiểm tra CSDL (chạy trong TablePlus hoặc psql)

-- 1. Thông tin một item và video nguồn
SELECT i.item_id, v.video_title, i.chapter_title, i.duration_sec, i.n_words,
       i.n_audio_segments, i.n_text_segments
FROM item i JOIN video v USING (video_id)
WHERE i.item_id = '001';

-- 2. Chuỗi đoạn audio của một item theo đúng thứ tự thời gian (đầu vào của cửa sổ trượt)
SELECT seg_index, start_sec, end_sec, n_voiced_frames, vector_dims(h_norm) AS dim_h, vector_dims(ecapa) AS dim_e
FROM audio_segment
WHERE item_id = '001'
ORDER BY seg_index;

-- 3. Giá trị một đặc trưng thủ công cụ thể (Mean F0) của các đoạn: tra vị trí qua feature_def
SELECT a.seg_index, (a.h_raw::real[])[f.feature_index + 1] AS f0_mean_hz
FROM audio_segment a, feature_def f
WHERE a.item_id = '001' AND f.feature_name = 'f0_mean'
ORDER BY a.seg_index;

-- 4. Độ tương đồng giọng nói (cosine ECAPA) giữa đoạn 0 của item 001 và mọi đoạn khác
--    (toán tử <=> của pgvector là khoảng cách cosine = 1 - cosine)
SELECT b.item_id, b.seg_index, 1 - (a.ecapa <=> b.ecapa) AS cosine
FROM audio_segment a, audio_segment b
WHERE a.item_id = '001' AND a.seg_index = 0 AND b.item_id <> '001'
ORDER BY cosine DESC
LIMIT 5;

-- 5. Từ khóa đại diện quan trọng nhất của một item
SELECT g.keyword, k.tf, round(k.tfidf::numeric, 2) AS tfidf
FROM item_keyword k JOIN keyword_group g USING (group_id)
WHERE k.item_id = '001'
ORDER BY k.tfidf DESC
LIMIT 10;

-- 6. Các biến thể đồng nghĩa được gộp vào một từ khóa đại diện
SELECT g.keyword, string_agg(m.term || ' (' || m.freq || ')', ', ' ORDER BY m.freq DESC) AS members
FROM keyword_group g JOIN keyword_member m USING (group_id)
GROUP BY g.group_id, g.keyword
HAVING count(*) > 1
ORDER BY sum(m.freq) DESC
LIMIT 10;

-- 7. Các item nhắc tới một từ khóa (theo bất kỳ biến thể nào), xếp theo TF-IDF
SELECT k.item_id, i.chapter_title, k.tf, round(k.tfidf::numeric, 2) AS tfidf
FROM keyword_member m
JOIN item_keyword k USING (group_id)
JOIN item i USING (item_id)
WHERE m.term = 'xe hơi'
ORDER BY k.tfidf DESC;

-- 8. Các thực thể được nhắc nhiều nhất trong toàn CSDL
SELECT e.text, e.label, sum(ie.count) AS total, count(*) AS n_items
FROM named_entity e JOIN item_entity ie USING (entity_id)
GROUP BY e.entity_id, e.text, e.label
ORDER BY total DESC
LIMIT 10;

-- 9. Tham số hệ thống (độ dài đoạn, thời lượng âm tiết, mô hình)
SELECT key, value FROM system_param WHERE key IN ('segment_sec', 'segment_syllables', 'models', 'keyword');
