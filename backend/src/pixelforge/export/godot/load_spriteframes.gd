# PixelForge sprite sheet loader (Godot 4.2+).
#
# Usage:
#   var frames := preload("res://load_spriteframes.gd").build("res://hero/walk.json")
#   $AnimatedSprite2D.sprite_frames = frames
#   $AnimatedSprite2D.play("walk_down")
#
# One animation is created per frameTag ("<animation>_<direction>"), using the
# fps and loop values stored in meta.x_autosprite.
extends RefCounted


static func build(json_path: String) -> SpriteFrames:
	var frames := SpriteFrames.new()
	var text := FileAccess.get_file_as_string(json_path)
	var data = JSON.parse_string(text)
	if typeof(data) != TYPE_DICTIONARY:
		push_error("PixelForge: cannot read atlas JSON: %s" % json_path)
		return frames

	var meta: Dictionary = data["meta"]
	var extra: Dictionary = meta.get("x_autosprite", {})
	var fps: float = float(extra.get("fps", 12))
	var loop: bool = bool(extra.get("loop", true))
	var texture := _load_texture(json_path.get_base_dir().path_join(meta["image"]))
	if texture == null:
		push_error("PixelForge: cannot load texture: %s" % meta["image"])
		return frames

	# Dictionary keeps insertion order, which matches the frameTag indices.
	var rects: Array = []
	for key in data["frames"].keys():
		var r: Dictionary = data["frames"][key]["frame"]
		rects.append(Rect2(r["x"], r["y"], r["w"], r["h"]))

	for tag in meta.get("frameTags", []):
		var anim_name: String = tag["name"]
		frames.add_animation(anim_name)
		frames.set_animation_speed(anim_name, fps)
		frames.set_animation_loop(anim_name, loop)
		for i in range(int(tag["from"]), int(tag["to"]) + 1):
			var atlas := AtlasTexture.new()
			atlas.atlas = texture
			atlas.region = rects[i]
			frames.add_frame(anim_name, atlas)

	if frames.has_animation("default"):
		frames.remove_animation("default")
	return frames


static func _load_texture(path: String) -> Texture2D:
	if path.begins_with("res://"):
		return load(path) as Texture2D
	var image := Image.load_from_file(path)
	if image == null:
		return null
	return ImageTexture.create_from_image(image)
