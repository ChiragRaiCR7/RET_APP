<!-- <template>
  <div class="upload-box">
    <input type="file" @change="onFileChange" />
    <button :disabled="!file || loading" @click="upload">
      {{ loading ? "Processing..." : "Upload & Convert" }}
    </button>

    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref } from "vue";

const file = ref(null);
const loading = ref(false);
const error = ref("");

function onFileChange(e) {
  file.value = e.target.files[0];
}

async function upload() {
  loading.value = true;
  error.value = "";

  const form = new FormData();
  form.append("file", file.value);

  try {
    const res = await fetch("http://127.0.0.1:8000/convert-archive", {
      method: "POST",
      body: form,
    });

    if (!res.ok) throw new Error("Conversion failed");

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = "converted_csv.zip";
    a.click();

    window.URL.revokeObjectURL(url);
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
</script>

<style>
.upload-box {
  margin-top: 2rem;
}
.error {
  color: red;
}
</style> -->
