# Headless check: godot --headless --script tests/godot/run_loader.gd -- <export_dir>
# Expects load_spriteframes.gd next to this script (or in res://).
extends SceneTree


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		push_error("usage: run_loader.gd -- <export_dir>")
		quit(2)
		return
	var dir := args[0]
	var loader = load("res://load_spriteframes.gd")
	var total := 0
	for file in DirAccess.get_files_at(dir):
		if not file.ends_with(".json") or file == "character.json":
			continue
		var frames: SpriteFrames = loader.build(dir.path_join(file))
		total += frames.get_animation_names().size()
	print("animations=%d" % total)
	quit(0)
