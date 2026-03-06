240:: 1768767252:0;ffmpeg -skip_frame nokey -i "/Users/evren/Downloads/Babe.1995/Babe.1995.mp4" -vsync vfr -frame_pts true out_%03d.png\
244:: 1768767252:0;ffmpeg -skip_frame nokey -i /Users/evren/Downloads/Babe.1995/Babe.1995.mp4 -vsync vfr \\
248:: 1768767252:0;ffmpeg -i /Users/evren/Downloads/Babe.1995/Babe.1995.mp4 -vsync vfr -q:v 2 \\
265:: 1768767252:0;ffmpeg -skip_frame nokey -i "/Users/evren/Downloads/Babe.1995/Babe.1995.mp4" -vsync vfr -frame_pts true out_%09d.png\
273:: 1768767252:0;ffmpeg -skip_frame nokey -i /Users/evren/Downloads/Babe.1995/Babe.1995.mp4 -vsync 0 -frame_pts 1 \\
276:: 1768767252:0;ffmpeg -skip_frame nokey -i input.mp4 -vsync 0 -frame_pts 1 \\
279:: 1768767252:0;ffmpeg -skip_frame nokey -i input.mp4 -vsync 0 -frame_pts 1 \\
282:: 1768767252:0;ffmpeg -skip_frame nokey -i input.mp4 -vsync 0 -frame_pts 1 \\
286:: 1768767252:0;ffmpeg -skip_frame nokey -i input.mp4 -vsync 0 -frame_pts 1 -vf "select='eq(pict_type\,I)'" key_%05d.png 2>&1
288:: 1768767252:0;aa use ffmpeg to get video frame-rate of input.mp4
289:: 1768767252:0;ffmpeg -i input.mp4 2>&1 | grep -oP '([0-9.]+) fps'
290:: 1768767252:0;ffmpeg -i input.mp4 2>&1 | grep -op '([0-9.]+) fps'
291:: 1768767252:0;ffmpeg -i input.mp4 2>&1 | grep -e '([0-9.]+) fps'
292:: 1768767252:0;ffmpeg -i input.mp4
293:: 1768767252:0;a use ffmpeg to get video frame-rate of input.mp4
297:: 1768767252:0;ffmpeg -i input.mp4 -vf "select='gt(scene,0.03)',showinfo" -vsync vfr out_%04d.png
299:: 1768767252:0;ffmpeg -i input.mp4 -vf "select='gt(scene,0.1)',showinfo" -vsync vfr out_%04d.png
301:: 1768767252:0;ffmpeg -i input.mp4 -vf "select='gt(scene,0.2)',showinfo" -vsync vfr -frame_pts 1 out_%010d.png
304:: 1768767252:0;ffmpeg -i input.mp4 -vf "select='isnan(prev_selected_t)+gte(t-prev_selected_t,1)+gt(scene,0.2)'" -vsync vfr -frame_pts 1 out_%010d.png
306:: 1768767252:0;ffmpeg -i input.mp4 -vf "select='isnan(prev_selected_t)+gte(t-prev_selected_t,5)+gt(scene,0.2)'" -vsync vfr -frame_pts 1 out_%010d.png
335:: 1768767252:0;ffmpeg -i input.webm -vf "select='isnan(prev_selected_t)+gte(t-prev_selected_t,5)+gt(scene,0.2)'" -vsync vfr -frame_pts 1 out_%010d.png
341:: 1768767252:0;history|grep ffmpeg
346:: 1768767252:0;history|grep ffmpeg
347:: 1768767252:0;ffmpeg -skip_frame nokey -i input.mp4 -vsync vfr -frame_pts true out_%03d.png
859:: 1768767252:0;ffmpeg -i sb.mp3 -af "asetrate=44100*0.995,aresample=44100" sb2.mp3
860:: 1768767252:0;ffmpeg -i sb.mp3 -af "asetrate=44100*1.005,aresample=44100" sb3.mp3
863:: 1768767252:0;ffmpeg -i "Go [OPFTkKeU1Jw].mp3" -af "asetrate=44100*1.005,aresample=44100" go01.mp3
869:: 1768767252:0;ffmpeg -i "sermaye.mp3" -af "asetrate=44100*1.005,aresample=44100" sermaye_2.mp3