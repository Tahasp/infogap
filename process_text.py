import re
def process_picot_text(text):
    """
    Processes PICOT structured text by splitting into paragraphs and filtering based on length.
    Stops processing if encountering a header named 'reference'.
    Stores data as key-value pairs where headers are keys and normal lines are stored as 'paragraph'.
    """
    lines = text.split('\n')  # Split by new line
    processed_paragraphs = []
    
    for line in lines:
        line = line.strip()
        
        # Detect headers using regex
        header_match = re.match(r'^(=+)(.*?)=+$', line)
        if header_match:
            header_text = header_match.group(2).strip().lower()
            if header_text == "参见":
                break  # Stop processing if 'reference' header is encountered
            processed_paragraphs.append({"header": header_text})
            continue
        
        # Store paragraph if it meets length requirement
        elif len(line) >= 6:
            processed_paragraphs.append({"paragraph": line})
    
    return processed_paragraphs
# Example usage
text = """月餅是一種甜品，通常在中秋节食用，因其形似满月而得名。中秋赏月吃月餅是中国文化的傳統風俗。月餅以「廣式月餅」、「潮式月餅」、「蘇式月餅」、「京式月餅」此四大派别最為普遍，此外其他各地还有各式不同種類的月饼，如：火腿月餅（雲南）、椒葱月餅（江西）、水晶月餅（潮汕）、薄酥月餅（湖南）、冬蓉月餅（廣東台山）、德懋恭水晶饼（陝西）、三白月餅（黑龍江）、海味月饼（山東）、雞絲月餅（清真式）、酥皮芋泥月餅（潮汕、福建、臺灣），港台分別有蛋黃酥、綠豆椪、芋頭酥和松子酥（臺灣）、奶黃月餅和冰皮月餅（香港）、松片（韓國）等。
== 溯源 ==
古代月饼被作為祭品于中秋节所食，現已成為中秋节食品和礼品。根據《洛中見聞》，唐僖宗曾在中秋節當日命令御膳房用紅綾將餅賞賜給新科進士。據說北宋之時，該種餅被稱為「宮餅」，在宮廷內流行，但也流傳到民間，當時俗稱「小餅」和「月團」，但此說並未有文獻核實。蘇東坡的〈留别廉守〉一詩曾經提及「小餅如嚼月，中有酥和飴」，不過詩中並未說明時序是在中秋。
「月饼」一词最早见于南宋，吴自牧《梦梁录》中，和芙蓉餅、菊花餅、梅花餅等並列，且屬於「市食點心，四時皆有」。
== 種類 ==
===A===
我是哦天上的三件套哦算了三大派别
== 参见 ==
冰皮月餅
鮮肉月餅
蛋黃酥：一種臺灣傳統月餅
Bánh pía：一種越南月餅，常做成甜零食包裝。
綠豆椪：一种臺湾传统月饼
綠豆餅：一种潮汕、臺湾传统喜餅，也作月饼
月光饼：一種香港、臺灣傳統月餅
月見团子（tsukimi dango つきみだんご）：日本的一种中秋節食品
吹上饼（fucha gi ふちゃぎ）：琉球的一种中秋節食品
松片：朝鮮半島的一种中秋節食品
月餅會
中秋博餅
雪糕月餅、冰淇淋月餅、雪餅：存放環境0℃以下，內餡是冰淇淋。
== 注释 ==
== 外部链接 =="""
processed = process_picot_text(text)
print(processed)