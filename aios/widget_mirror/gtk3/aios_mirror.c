/* GTK3 Widget Mirror — GTK_MODULES=aios-mirror
 * Real loadable module: publishes POSIX shm header /aios-mirror-<pid>
 * for dcpd Mode-A. Widget tree expansion is versioned; v1 ships window title + seq.
 */
#include <gtk/gtk.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/mman.h>
#include <sys/stat.h>

#define AIOS_MIRROR_MAGIC 0x41314D52u
#define AIOS_MIRROR_VER 1

typedef struct {
  guint32 magic;
  guint32 ver;
  guint32 pid;
  guint32 seq;
  guint32 n_widgets;
  guint32 reserved;
  char title[128];
} AiosMirrorHeader;

static int g_fd = -1;
static AiosMirrorHeader *g_map = NULL;
static guint32 g_seq = 0;
static char g_shm_name[64];

static void mirror_publish(GtkWidget *widget) {
  const char *title = "";
  if (!g_map)
    return;
  if (widget && GTK_IS_WINDOW(widget)) {
    const gchar *t = gtk_window_get_title(GTK_WINDOW(widget));
    if (t)
      title = t;
  }
  g_seq++;
  g_map->magic = AIOS_MIRROR_MAGIC;
  g_map->ver = AIOS_MIRROR_VER;
  g_map->pid = (guint32)getpid();
  g_map->seq = g_seq;
  g_map->n_widgets = widget ? 1u : 0u;
  g_map->reserved = 0;
  snprintf(g_map->title, sizeof(g_map->title), "%s", title);
}

static gboolean on_tick(gpointer data) {
  GList *toplevels;
  (void)data;
  toplevels = gtk_window_list_toplevels();
  if (toplevels) {
    mirror_publish(GTK_WIDGET(toplevels->data));
    g_list_free(toplevels);
  }
  return G_SOURCE_CONTINUE;
}

static void open_shm(void) {
  snprintf(g_shm_name, sizeof(g_shm_name), "/aios-mirror-%d", getpid());
  g_fd = shm_open(g_shm_name, O_CREAT | O_RDWR, 0600);
  if (g_fd < 0) {
    fprintf(stderr, "aios-mirror: shm_open: %s\n", strerror(errno));
    return;
  }
  if (ftruncate(g_fd, (off_t)sizeof(AiosMirrorHeader)) != 0) {
    fprintf(stderr, "aios-mirror: ftruncate failed\n");
    return;
  }
  g_map = mmap(NULL, sizeof(AiosMirrorHeader), PROT_READ | PROT_WRITE, MAP_SHARED, g_fd, 0);
  if (g_map == MAP_FAILED) {
    g_map = NULL;
    fprintf(stderr, "aios-mirror: mmap failed\n");
  }
}

G_MODULE_EXPORT void gtk_module_init(gint *argc, gchar ***argv[]) {
  (void)argc;
  (void)argv;
  open_shm();
  g_timeout_add(200, on_tick, NULL);
  fprintf(stderr, "aios-mirror: loaded pid=%d shm=%s\n", getpid(), g_shm_name);
}
