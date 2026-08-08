<template>
  <el-form :model="form" label-width="90px" class="lf">
    <el-row :gutter="16">
      <el-col :span="12">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="地点名称" />
        </el-form-item>
      </el-col>
      <el-col :span="12">
        <el-form-item label="类型">
          <el-select v-model="form.location_type" placeholder="选择类型" clearable style="width:100%">
            <el-option label="城市" value="城市" />
            <el-option label="秘境" value="秘境" />
            <el-option label="洞府" value="洞府" />
            <el-option label="门派" value="门派" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-form-item label="所属位面">
          <el-select v-model="form.plane" placeholder="选择或输入位面" clearable filterable allow-create
            default-first-option style="width:100%">
            <el-option v-for="p in planePresets" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
      </el-col>
      <el-col :span="12">
        <el-form-item label="所属区域">
          <el-input v-model="form.region" placeholder="如：东域 / 北境" />
        </el-form-item>
      </el-col>
    </el-row>

    <el-form-item label="描述">
      <el-input v-model="form.description" type="textarea" :rows="3" resize="none" placeholder="地理环境、氛围、关键设定…" />
    </el-form-item>

    <el-divider content-position="left">空间坐标（统一世界坐标系：x 向东、y 向北、height 为高度）</el-divider>

    <el-row :gutter="16">
      <el-col :span="8">
        <el-form-item label="中心 X">
          <el-input-number v-model="form.center_x" :controls="false" :precision="2" style="width:100%" placeholder="横坐标" />
        </el-form-item>
      </el-col>
      <el-col :span="8">
        <el-form-item label="中心 Y">
          <el-input-number v-model="form.center_y" :controls="false" :precision="2" style="width:100%" placeholder="纵坐标" />
        </el-form-item>
      </el-col>
      <el-col :span="8">
        <el-form-item label="高度">
          <el-input-number v-model="form.height" :controls="false" :precision="2" style="width:100%" placeholder="海拔/楼层" />
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-form-item label="形状">
          <el-select v-model="form.shape" placeholder="选择形状（默认点）" clearable style="width:100%">
            <el-option label="点" value="point" />
            <el-option label="圆形" value="circle" />
            <el-option label="矩形" value="rect" />
            <el-option label="扇形" value="sector" />
            <el-option label="多边形" value="polygon" />
          </el-select>
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="16" v-if="form.shape && form.shape !== 'point'">
      <el-col :span="8" v-if="form.shape !== 'rect'">
        <el-form-item label="半径">
          <el-input-number v-model="form.radius" :controls="false" :precision="2" style="width:100%" />
        </el-form-item>
      </el-col>
      <el-col :span="8" v-if="form.shape === 'rect'">
        <el-form-item label="半宽(a)">
          <el-input-number v-model="form.radius" :controls="false" :precision="2" style="width:100%" />
        </el-form-item>
      </el-col>
      <el-col :span="8" v-if="form.shape === 'rect'">
        <el-form-item label="半高(b)">
          <el-input-number v-model="form.radius_y" :controls="false" :precision="2" style="width:100%" />
        </el-form-item>
      </el-col>
    </el-row>

    <el-row :gutter="16" v-if="form.shape === 'sector'">
      <el-col :span="12">
        <el-form-item label="朝向(度)">
          <el-input-number v-model="form.angle" :controls="false" :precision="1" style="width:100%" />
        </el-form-item>
      </el-col>
      <el-col :span="12">
        <el-form-item label="张角(度)">
          <el-input-number v-model="form.angle_span" :controls="false" :precision="1" style="width:100%" />
        </el-form-item>
      </el-col>
    </el-row>

    <el-form-item label="多边形" v-if="form.shape === 'polygon'">
      <el-input v-model="polygonText" type="textarea" :rows="3" resize="none"
        placeholder='顶点 JSON，如 [[0,0],[10,0],[10,10],[0,10]]' />
    </el-form-item>

    <el-form-item label="特色地标">
      <el-select v-model="form.notable_features" multiple filterable allow-create default-first-option
        placeholder="输入地标后回车添加，可多个" style="width:100%">
        <el-option v-for="f in form.notable_features" :key="f" :label="f" :value="f" />
      </el-select>
    </el-form-item>
  </el-form>
</template>

<script setup>
import { defineModel, ref, watch } from 'vue'

const form = defineModel({ type: Object, required: true })
const planePresets = ['主世界', '凡间', '仙界', '灵界', '地狱', '秘境', '魔界']

const polygonText = ref('')
watch(() => form.value.polygon, (v) => {
  polygonText.value = v ? JSON.stringify(v) : ''
}, { immediate: true })
watch(polygonText, (t) => {
  if (!t || !t.trim()) { form.value.polygon = null; return }
  try {
    const arr = JSON.parse(t)
    form.value.polygon = Array.isArray(arr) ? arr : null
  } catch (e) {
    // 解析失败暂不改写，保存时由后端校验
  }
})
</script>

<style scoped>
.lf { padding: 4px 8px 0; }
</style>
