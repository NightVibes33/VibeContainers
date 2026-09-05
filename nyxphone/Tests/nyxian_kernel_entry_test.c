#include "NyxRuntime.h"

#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>

static char logs[4096];
static size_t logs_length;

static void capture(const uint8_t *bytes, size_t length, void *context) {
    (void)context;
    size_t available = sizeof(logs) - 1 - logs_length;
    if (length > available) length = available;
    memcpy(logs + logs_length, bytes, length);
    logs_length += length;
    logs[logs_length] = 0;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    FILE *file = fopen(argv[1], "rb");
    if (!file) return 3;
    if (fseek(file, 0, SEEK_END) != 0) return 4;
    long file_size = ftell(file);
    if (file_size <= 0 || fseek(file, 0, SEEK_SET) != 0) return 5;
    uint8_t *image = (uint8_t *)malloc((size_t)file_size);
    if (!image) return 6;
    if (fread(image, 1, (size_t)file_size, file) != (size_t)file_size) return 7;
    fclose(file);

    char disk_path[] = "/tmp/viphone-disk-XXXXXX";
    int disk_fd = mkstemp(disk_path);
    if (disk_fd < 0 || close(disk_fd) != 0) return 8;

    NyxVMConfig config = {1, 16u * 1024u * 1024u, 1290, 2796, 460, 3.0};
    NyxVM *vm = nyx_vm_create(&config);
    if (!vm) return 9;
    if (nyx_vm_mount_disk(vm, disk_path, 1024u * 1024u) != 0) return 10;
    nyx_vm_set_log_callback(vm, capture, NULL);
    if (nyx_vm_load_kernel_bytes(vm, image, (size_t)file_size, 0x100000, 0x100000) != 0) return 9;
    int32_t start_status = nyx_vm_start(vm);
    if (start_status != 0 && start_status != 8) return 10;
    if (nyx_vm_instructions_retired(vm) < 15) return 11;
    if (!strstr(logs, "[NYXRT] runtime initialized")) return 12;
    if (!strstr(logs, "[NYXRT] Nyxian loaded")) return 13;
    if (!strstr(logs, "[NYXIAN] kernel entry reached")) return 14;
    if (!strstr(logs, "[NYXDARWIN] nyxinit started")) return 15;
    if (!strstr(logs, "hello from Nyxian userspace")) return 16;
    if (!strstr(logs, "[NYXDISPLAY] first frame")) return 19;
    if (!strstr(logs, "[NYXSTORAGE] root mounted")) return 20;
    if (!strstr(logs, "[NYXNET] HTTPS request complete")) return 27;
    if (strstr(logs, "[NYXNET] HTTPS request failed")) return 28;
    if (!strstr(logs, "[NYXDARWIN] basic ABI passed")) return 38;
    if (!strstr(logs, "[NYXMACH] IPC roundtrip passed")) return 39;
    uint8_t frame[64u * 96u * 4u] = {0};
    NyxFramebufferInfo frame_info = {0};
    if (nyx_vm_copy_framebuffer(vm, frame, sizeof(frame), &frame_info) != 0) return 18;
    if (frame_info.width != 64 || frame_info.height != 96 || frame_info.stride != 256) return 19;
    if (frame_info.pixel_format != 1 || frame_info.byte_length != sizeof(frame)) return 20;
    if (frame[0] == 0 && frame[1] == 0 && frame[2] == 0 && frame[3] == 0) return 21;
    if (memcmp(frame, frame + sizeof(frame) - 4, 4) != 0) return 22;
    uint8_t first_pixel[4];
    memcpy(first_pixel, frame, sizeof(first_pixel));
    NyxTouchEvent touch = {7u, 0.25f, 0.75f, 1.0f, 0u};
    if (nyx_vm_touch_capture_frame(vm, &touch, frame, sizeof(frame), &frame_info) != 0) return 23;
    if (memcmp(first_pixel, frame, sizeof(first_pixel)) == 0) return 24;
    if (!strstr(logs, "[NYXTOUCH] event delivered")) return 25;
    if (nyx_vm_state(vm) != 5u) return 26;
    fputs(logs, stdout);
    nyx_vm_destroy(vm);

    logs_length = 0;
    logs[0] = 0;
    NyxVM *second_vm = nyx_vm_create(&config);
    if (!second_vm) return 30;
    if (nyx_vm_mount_disk(second_vm, disk_path, 1024u * 1024u) != 0) return 31;
    nyx_vm_set_log_callback(second_vm, capture, NULL);
    if (nyx_vm_load_kernel_bytes(second_vm, image, (size_t)file_size, 0x100000, 0x100000) != 0) return 32;
    start_status = nyx_vm_start(second_vm);
    if (start_status != 0 && start_status != 8) return 33;
    if (!strstr(logs, "[NYXSTORAGE] root mounted")) return 34;
    if (!strstr(logs, "[NYXNET] HTTPS request complete")) return 37;
    if (!strstr(logs, "[NYXMACH] IPC roundtrip passed")) return 40;
    nyx_vm_destroy(second_vm);

    disk_fd = open(disk_path, O_RDONLY);
    uint64_t persisted_boots = 0;
    if (disk_fd < 0) return 35;
    const ssize_t persisted_read = read(disk_fd, &persisted_boots, sizeof(persisted_boots));
    if (persisted_read != (ssize_t)sizeof(persisted_boots)) return 35;
    close(disk_fd);
    unlink(disk_path);
    if (persisted_boots != 2) return 36;
    puts("[NYXSTORAGE] persistence verified across VM recreation");
    free(image);
    return 0;
}
