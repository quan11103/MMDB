"""
Cấu hình trích rút đặc trưng — Nhóm 24.
Mọi tham số đã chốt nằm ở đây; các module khác chỉ đọc từ file này.
Giá trị đánh dấu [THỰC NGHIỆM] cần chọn lại sau khi chạy thử.
"""

# ---------------------------------------------------------------
# 1. Tiền xử lý âm thanh
# ---------------------------------------------------------------
SAMPLE_RATE = 16000          # toàn bộ audio đưa về 16 kHz
MONO = True                  # stereo -> mono (trung bình 2 kênh, do FFmpeg thực hiện)

# Chia đoạn theo âm tiết (yêu cầu của giảng viên): file CSDL và file truy vấn được chia thành các đoạn
# cùng độ dài rồi so khớp bằng cửa sổ trượt (segmenting.py).
#   độ dài đoạn audio = SEGMENT_SYLLABLES x thời lượng TB 1 âm tiết (đo trên dataset -> syllable_stats.json)
#   độ dài đoạn text  = SEGMENT_SYLLABLES từ
SEGMENT_SYLLABLES = 40
SEGMENT_ROUND_SEC = True     # làm tròn độ dài đoạn audio tới giây gần nhất (40 x 0,249 s = 9,97 s -> 10 s)

# Khung phân tích dùng chung (RMS, ZCR, phổ, MFCC) — tính BÊN TRONG mỗi đoạn
FRAME_MS = 25
HOP_MS = 10
FRAME_LENGTH = int(SAMPLE_RATE * FRAME_MS / 1000)   # 400 mẫu
HOP_LENGTH = int(SAMPLE_RATE * HOP_MS / 1000)       # 160 mẫu
N_FFT = 512                  # FFT 512 điểm (zero-padding khung 400 mẫu)
WINDOW = "hamming"

# ---------------------------------------------------------------
# 2. Miền thời gian
# ---------------------------------------------------------------
SILENCE_DB_BELOW_MAX = 40.0  # khung im lặng: RMS thấp hơn RMS lớn nhất của đoạn 40 dB

# ---------------------------------------------------------------
# 3. Cao độ & chất lượng giọng (Praat / parselmouth)
# ---------------------------------------------------------------
PITCH_FLOOR = 75.0           # Hz
PITCH_CEILING = 500.0        # Hz
PITCH_TIME_STEP = 0.01       # s
# Tham số chuẩn của Praat cho Jitter/Shimmer
PERIOD_FLOOR = 0.0001
PERIOD_CEILING = 0.02
MAX_PERIOD_FACTOR = 1.3
MAX_AMPLITUDE_FACTOR = 1.6
# HNR: To Harmonicity (cc)
HNR_TIME_STEP = 0.01
HNR_SILENCE_THRESHOLD = 0.1
HNR_PERIODS_PER_WINDOW = 1.0

# ---------------------------------------------------------------
# 4. Formant (Praat To Formant (burg), LPC)
# ---------------------------------------------------------------
N_FORMANTS_LPC = 5           # 5 formant -> bậc LPC = 10
MAX_FORMANT_HZ = 5500.0      # một giá trị cố định cho mọi người nói
FORMANT_WINDOW = 0.025       # s
FORMANT_PRE_EMPHASIS = 50.0  # Hz

# ---------------------------------------------------------------
# 5. MFCC
# ---------------------------------------------------------------
N_MFCC = 13                  # C0..C12
N_MELS = 26                  # [THỰC NGHIỆM] 26 hoặc 40
DELTA_WIDTH = 5              # N = 2 theo HTK

# ---------------------------------------------------------------
# 6. ECAPA-TDNN
# ---------------------------------------------------------------
ECAPA_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
ECAPA_SAVEDIR = "pretrained_models/spkrec-ecapa-voxceleb"
ECAPA_BATCH = 8              # số đoạn mỗi lô; đoạn dùng chung cách chia của segmenting.py

# ---------------------------------------------------------------
# 7. Sentence Transformer (dùng chung cho keywords và vector ngữ nghĩa)
# ---------------------------------------------------------------
ST_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
ST_BATCH = 64
# Chunk văn bản = SEGMENT_SYLLABLES từ, không chồng lấn (segmenting.text_chunks)

# ---------------------------------------------------------------
# 8. NER (underthesea)
# ---------------------------------------------------------------
NER_LABELS = ("PER", "ORG", "LOC")
NER_PIECE_WORDS = 200        # cắt transcript dài thành các đoạn ~200 từ trước khi gọi NER

# ---------------------------------------------------------------
# 9. Keywords — từ điển chung toàn dataset
# ---------------------------------------------------------------
# Từ loại của underthesea (bộ nhãn VLSP)
HEAD_POS = ("N", "Np", "Nb", "Ny", "FW")          # từ đầu cụm phải là danh từ
MODIFIER_POS = ("N", "Np", "Nb", "Ny", "FW", "A")  # các từ theo sau: danh từ hoặc tính từ
NGRAM_MAX = 3                # cụm 1..3 từ (từ đã tách bằng underthesea)
MIN_FREQ_IN_FILE = 2         # ứng viên phải xuất hiện >= 2 lần trong 1 file
MAX_CANDIDATES = 8000        # giới hạn số ứng viên đưa vào gom nhóm (bộ nhớ O(n^2))
KEYWORD_SIM_THRESHOLD = 0.90 # chọn bằng thực nghiệm (keyword_threshold_report)
KEYWORD_LINKAGE = "complete" # "average" hoặc "complete" (complete ít gộp nhầm hơn qua thực nghiệm)
TOP_K_KEYWORDS = 20          # số từ khóa đại diện lưu cho mỗi file (theo TF-IDF)
# Danh sách từ dừng tiếng Việt (github.com/stopwords/vietnamese-stopwords, ~1.900 từ),
# cộng thêm danh sách bổ sung trong content_text.py
import os as _os
STOPWORDS_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "vietnamese-stopwords.txt")
# Quy tắc từ 1 âm tiết: embedding của từ tiếng Việt 1 âm tiết đứng riêng không đủ tin cậy,
# nên từ 1 âm tiết chỉ ở lại nhóm khi nó là một âm tiết của một cụm từ trong cùng nhóm.
SPLIT_MONOSYLLABLE_GROUPS = True
