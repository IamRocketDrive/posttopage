from flask import Flask, request, jsonify
import instaloader
import re
import requests
import os
import time
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator

app = Flask(__name__)
L = instaloader.Instaloader(dirname_pattern="downloaded")

def extract_shortcode(url):
    print("กำลังแยก shortcode จาก URL:", url)
    clean_url = url.split('?')[0]
    match = re.search(r'/(?:reel|p|tv)/([A-Za-z0-9_-]{5,})', clean_url)
    if not match:
        print("ไม่พบ shortcode ใน URL:", url)
    return match.group(1) if match else None

def clean_downloaded_folder():
    print("กำลังล้างโฟลเดอร์ downloaded")
    folder = "downloaded"
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        if os.path.isfile(file_path):
            print(f"กำลังลบไฟล์: {file_path}")
            os.remove(file_path)

def upscale_video(video_path, target_width=540, target_height=960):
    print(f"กำลังตรวจสอบและ upscale วิดีโอ: {video_path}")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("ไม่สามารถเปิดวิดีโอได้")
        return video_path

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"ขนาดวิดีโอดั้งเดิม: {width}x{height}")

    if width >= target_width and height >= target_height:
        print("ขนาดวิดีโอเพียงพอ ไม่ต้อง upscale")
        cap.release()
        return video_path

    # คำนวณอัตราส่วนเพื่อรักษา aspect ratio
    aspect_ratio = width / height
    target_aspect = target_width / target_height

    if aspect_ratio > target_aspect:
        # วิดีโอกว้างเกินไป ปรับตามความสูง
        new_height = target_height
        new_width = int(new_height * aspect_ratio)
    else:
        # วิดีโอสูงเกินไป ปรับตามความกว้าง
        new_width = target_width
        new_height = int(new_width / aspect_ratio)

    # ปรับขนาดให้เป็นจำนวนคู่ (จำเป็นสำหรับบาง codec)
    new_width = new_width + (new_width % 2)
    new_height = new_height + (new_height % 2)

    output_path = os.path.join(os.path.dirname(video_path), "upscaled_video.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    fps = cap.get(cv2.CAP_PROP_FPS)
    out = cv2.VideoWriter(output_path, fourcc, fps, (new_width, new_height))

    print(f"กำลัง upscale เป็นขนาด: {new_width}x{new_height}")
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        # Upscale เฟรม
        upscaled_frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
        out.write(upscaled_frame)

    cap.release()
    out.release()
    print(f"upscale เสร็จสิ้น บันทึกที่: {output_path}")
    return output_path

# ปรับปรุงฟังก์ชัน download_video เพื่อรวมการตรวจสอบและ upscale
def download_video(shortcode):
    print("กำลังดาวน์โหลดวิดีโอด้วย shortcode:", shortcode)
    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        print("ดึงโพสต์สำเร็จ, เริ่มดาวน์โหลด")
        L.download_post(post, target=shortcode)
        for f in os.listdir("downloaded"):
            if f.endswith(".mp4"):
                print("พบไฟล์วิดีโอ:", f)
                video_path = os.path.join("downloaded", f)
                # ตรวจสอบและ upscale วิดีโอ
                return upscale_video(video_path)
    except Exception as e:
        print("เกิดข้อผิดพลาดในการดาวน์โหลด:", e)
    return None

def add_caption_to_video(video_path, caption):
    print("กำลังเพิ่มแคปชันลงในวิดีโอ:", video_path)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("ไม่สามารถเปิดวิดีโอได้:", video_path)
        return
    print("เปิดวิดีโอสำเร็จ")

    output_path = os.path.join(os.path.dirname(__file__), "./modified_video.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    print(f"ตั้งค่าเอาต์พุตวิดีโอ: {output_path}, FPS: {fps}, ขนาด: {width}x{height}")

    font_path = os.path.join(os.path.dirname(__file__), "NotoSansThai-Bold.ttf")
    try:
        font = ImageFont.truetype(font_path, 50)
        print("โหลดฟอนต์สำเร็จ:", font_path)
    except IOError:
        print(f"ไม่สามารถโหลดฟอนต์ได้จาก: {font_path}")
        return

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            print("สิ้นสุดการอ่านเฟรม")
            break
        frame_count += 1
        #print(f"กำลังประมวลผลเฟรมที่: {frame_count}")

        img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        bbox = draw.textbbox((0, 0), caption, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (img_pil.width - w) // 2
        y = 100

        draw.text((x, y), caption, font=font, fill=(255, 255, 255))
        frame = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        out.write(frame)
        #print(f"เขียนเฟรม {frame_count} ไปที่ไฟล์")

    cap.release()
    out.release()

    print(f"เสร็จสิ้น: เขียน {frame_count} เฟรมลงในไฟล์ {output_path}")
    return output_path

def check_reel_status(video_id, access_token):
    print("กำลังตรวจสอบสถานะ reel:", video_id)
    url = f"https://graph.facebook.com/v22.0/{video_id}"
    params = {"access_token": access_token, "fields": "status"}
    for attempt in range(10):
        print(f"พยายามตรวจสอบครั้งที่ {attempt + 1}")
        res = requests.get(url, params=params)
        if res.status_code == 200:
            status = res.json().get("status", {}).get("video_status")
            print(f"สถานะ reel: {status}")
            if status == "ready":
                print("reel พร้อมใช้งาน")
                return True
        time.sleep(30)
        print("รอ 30 วินาทีก่อนตรวจสอบครั้งถัดไป")
    print("หมดเวลาตรวจสอบสถานะ reel")
    return False

def upload_reel_from_file(video_path, description, page_id, access_token):
    print("เริ่มอัปโหลด reel จากไฟล์:", video_path)
    start_url = f"https://graph.facebook.com/v22.0/{page_id}/video_reels"
    print("ส่งคำขอเริ่มอัปโหลด")
    start_res = requests.post(start_url, json={
        "upload_phase": "start",
        "access_token": access_token
    })
    if start_res.status_code != 200:
        print("เริ่มอัปโหลดล้มเหลว:", start_res.json())
        return {"error": "Start upload failed", "details": start_res.json()}

    video_id = start_res.json().get("video_id")
    upload_url = start_res.json().get("upload_url")
    print(f"ได้รับ video_id: {video_id}, upload_url: {upload_url}")

    file_size = os.path.getsize(video_path)
    headers = {
        "Authorization": f"OAuth {access_token}",
        "offset": "0",
        "file_size": str(file_size)
    }
    print(f"อัปโหลดวิดีโอ, ขนาดไฟล์: {file_size} ไบต์")
    with open(video_path, "rb") as f:
        upload_res = requests.post(upload_url, headers=headers, data=f)
    if not upload_res.ok:
        print("อัปโหลดวิดีโอล้มเหลว:", upload_res.json())
        return {"error": "Video upload failed", "details": upload_res.json()}

    finish_url = f"https://graph.facebook.com/v22.0/{page_id}/video_reels"
    print("ส่งคำขอสิ้นสุดการอัปโหลด")
    finish_res = requests.post(finish_url, params={
        "access_token": access_token,
        "video_id": video_id,
        "upload_phase": "finish",
        "video_state": "PUBLISHED",
        "description": description
    })
    result = finish_res.json()
    result["id"] = video_id
    print("ผลลัพธ์การอัปโหลด:", result)
    return result

def create_unpublished_photo(media_url, page_id, access_token):
    print("สร้างรูปภาพที่ยังไม่เผยแพร่จาก URL:", media_url)
    res = requests.post(
        f"https://graph.facebook.com/v19.0/{page_id}/photos",
        data={
            "url": media_url,
            "published": "false",
            "access_token": access_token
        }
    )
    print("ผลลัพธ์การสร้างรูปภาพ:", res.json())
    return res.json().get("id")

def publish_album(media_ids, caption, page_id, access_token):
    print("เผยแพร่อัลบั้มด้วย media_ids :", media_ids)
    attached_media = [{"media_fbid": mid} for mid in media_ids]
    res = requests.post(
        f"https://graph.facebook.com/v19.0/{page_id}/feed",
        json={
            "message": caption,
            "attached_media": attached_media,
            "access_token": access_token
        }
    )
    print("ผลลัพธ์การเผยแพร่อัลบั้ม:", res.json())
    return res.json()

def post_comment(post_id, comment, access_token):
    print(f"โพสต์คอมเมนต์ไปที่ post_id: {post_id}, ข้อความ: {comment}")
    res = requests.post(
        f"https://graph.facebook.com/v19.0/{post_id}/comments",
        data={
            "message": comment,
            "access_token": access_token
        }
    )
    print("ผลลัพธ์การโพสต์คอมเมนต์:", res.json())
    return res.json()

def post_comment_with_image(post_id, comment, image_url, access_token):
    print(f"โพสต์คอมเมนต์พร้อมรูปภาพไปที่ post_id: {post_id}, ข้อความ: {comment}, รูปภาพ: {image_url}")
    res = requests.post(
        f"https://graph.facebook.com/v19.0/{post_id}/comments",
        data={
            "message": comment,
            "attachment_url": image_url,
            "access_token": access_token
        }
    )
    print("ผลลัพธ์การโพสต์คอมเมนต์พร้อมรูปภาพ:", res.json())
    return res.json()

def translate_to_thai(text):
    print("กำลังแปลข้อความเป็นภาษาไทย:", text)
    try:
        translated = GoogleTranslator(source='auto', target='th').translate(text)
        print("แปลสำเร็จ:", translated)
        return translated
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการแปล: {e}")
        return text

@app.route('/fetch', methods=['POST'])
def fetch_instagram():
    print("ได้รับคำขอ POST ที่ /fetch")
    data = request.get_json()
    print("ข้อมูลที่ได้รับ:", data)
    url = data.get("url")
    caption_n8n = data.get("caption") or ""
    video_caption = data.get("videoCaption")
    text_overlay = data.get("Text_on_video")
    access_token = data.get("access_token")
    page_id = data.get("page_id")

    if not url or not access_token or not page_id:
        print("ขาดฟิลด์ที่จำเป็น: url, access_token, page_id")
        return jsonify({"success": False, "message": "Missing required fields (url, access_token, page_id)"}), 400

    shortcode = extract_shortcode(url)
    if not shortcode:
        print("URL Instagram ไม่ถูกต้อง")
        return jsonify({"success": False, "message": "Invalid Instagram URL"}), 400

    try:
        print("กำลังดึงโพสต์ Instagram ด้วย shortcode:", shortcode)
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        print("ดึงโพสต์ Instagram สำเร็จ")

        caption_combined = (post.caption or "") + " " + caption_n8n.strip()
        print("แคปชันที่รวม:", caption_combined)
        translated_caption = translate_to_thai(caption_combined)
        print("แคปชันที่แปลแล้ว:", translated_caption)

        if post.is_video:
            print("โพสต์เป็นวิดีโอ, เริ่มดาวน์โหลด")
            video_path = download_video(shortcode)
            if not video_path:
                print("ดาวน์โหลดวิดีโอล้มเหลว")
                return jsonify({"success": False, "message": "Download video failed"}), 500

            if video_caption:
                print("เพิ่มแคปชันลงในวิดีโอ:", video_caption)
                video_path = add_caption_to_video(video_path, video_caption)

            print("อัปโหลด reel ไปที่ Facebook")
            response = upload_reel_from_file(video_path, translated_caption, page_id, access_token)
            print("ล้างโฟลเดอร์ downloaded")
            clean_downloaded_folder()

            if response.get("id"):
                print("อัปโหลด reel สำเร็จ, ตรวจสอบสถานะ")
                if check_reel_status(response["id"], access_token):
                    print("reel พร้อมใช้งาน, เริ่มโพสต์คอมเมนต์")
                    comment_responses = []
                    i = 1
                    try:
                        while True:
                            comment = data.get(f"comment{i}")
                            if not comment:
                                print("ไม่มีคอมเมนต์เพิ่มเติมสำหรับ reel")
                                break
                            comment_image_url = data.get(f"comment{i}_image_url")
                            print(f"ตรวจสอบข้อมูลคอมเมนต์ {i}:", comment, "รูปภาพ:", comment_image_url)
                            if comment_image_url:
                                print(f"โพสต์คอมเมนต์ {i} พร้อมรูปภาพ")
                                res = post_comment_with_image(response["id"], comment, comment_image_url, access_token)
                            else:
                                print(f"โพสต์คอมเมนต์ {i} ปกติ")
                                res = post_comment(response["id"], comment, access_token)
                            comment_responses.append(res)
                            print(f"ผลลัพธ์คอมเมนต์ {i}:", res)
                            i += 1
                        if not comment_responses:
                            print("ไม่มีคอมเมนต์ให้โพสต์สำหรับ reel")
                        return jsonify({
                            "success": True,
                            "message": "Reel uploaded and commented successfully",
                            "reel_id": response["id"],
                            "comment_responses": comment_responses
                        })
                    except Exception as e:
                        print("เกิดข้อผิดพลาดในการโพสต์คอมเมนต์:", str(e))
                        return jsonify({
                            "success": False,
                            "message": "Reel uploaded but failed to post comment",
                            "reel_id": response["id"],
                            "error": str(e)
                        }), 500
                else:
                    print("หมดเวลาหรืออัปโหลด reel ล้มเหลว")
                    return jsonify({
                        "success": False,
                        "message": "Reel upload timed out or failed to process"
                    }), 500
            else:
                print("อัปโหลด reel ล้มเหลว:", response)
                return jsonify({
                    "success": False,
                    "message": "Reel upload failed",
                    "result": response
                }), 500

        else:
            print("โพสต์เป็นรูปภาพหรืออัลบั้ม")
            media_ids = []
            if post.typename == "GraphSidecar":
                print("โพสต์เป็นอัลบั้ม, ดึงรูปภาพทั้งหมด")
                for node in post.get_sidecar_nodes():
                    if not node.is_video:
                        print("สร้างรูปภาพที่ยังไม่เผยแพร่:", node.display_url)
                        mid = create_unpublished_photo(node.display_url, page_id, access_token)
                        if mid:
                            media_ids.append(mid)
                            print("เพิ่ม media_id:", mid)
            else:
                print("โพสต์เป็นรูปภาพเดี่ยว:", post.url)
                mid = create_unpublished_photo(post.url, page_id, access_token)
                if mid:
                    media_ids.append(mid)
                    print("เพิ่ม media_id:", mid)

            if not media_ids:
                print("ไม่พบรูปภาพที่ถูกต้อง")
                return jsonify({"success": False, "message": "No valid images found"}), 400

            print("เผยแพร่อัลบั้มด้วยแคปชัน:", translated_caption)
            album_response = publish_album(media_ids, translated_caption, page_id, access_token)
            post_id = album_response.get("id")
            print("โพสต์อัลบั้มสำเร็จ, post_id:", post_id)

            i = 1
            comment_responses = []
            while True:
                text = data.get(f"comment{i}")
                if not text:
                    print("ไม่มีคอมเมนต์เพิ่มเติม")
                    break
                image_url = data.get(f"comment{i}_image_url")
                if image_url:
                    print(f"โพสต์คอมเมนต์ {i} พร้อมรูปภาพ:", image_url)
                    res = post_comment_with_image(post_id, text, image_url, access_token)
                else:
                    print(f"โพสต์คอมเมนต์ {i} ปกติ:", text)
                    res = post_comment(post_id, text, access_token)
                comment_responses.append(res)
                print(f"ผลลัพธ์คอมเมนต์ {i}:", res)
                i += 1

            print("โพสต์สำเร็จทั้งหมด")
            return jsonify({
                "success": True,
                "message": "โพสต์สำเร็จ",
                "post_id": post_id
            })

    except Exception as e:
        error_msg = str(e)
        print("เกิดข้อผิดพลาด:", error_msg)
        if "Fetching Post metadata failed" in error_msg:
            print("ไม่สามารถดึงข้อมูลโพสต์ Instagram ได้")
            return jsonify({
                "success": False,
                "message": "ไม่สามารถดึงข้อมูลโพสต์จาก Instagram ได้ (อาจเป็นโพสต์ private หรือโดนลบ)",
                "error": error_msg
            }), 500

        print("ข้อผิดพลาดไม่ทราบสาเหตุ")
        return jsonify({
            "success": False,
            "message": "เกิดข้อผิดพลาดไม่ทราบสาเหตุ",
            "error": error_msg
        }), 500

if __name__ == '__main__':
    print("สร้างโฟลเดอร์ downloaded หากยังไม่มี")
    os.makedirs("downloaded", exist_ok=True)
    print("เริ่มรัน Flask server ที่ port 5001")
    app.run(host="0.0.0.0", port=5001)
