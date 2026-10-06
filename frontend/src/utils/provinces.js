/* 省份编码 → 中文名映射与名称规范化（全国/省两级地图与统计共用） */

export const provinceNames = {
  anhui: "安徽",
  beijing: "北京",
  chongqing: "重庆",
  fujian: "福建",
  gansu: "甘肃",
  guangdong: "广东",
  guangxi: "广西",
  guizhou: "贵州",
  hainan: "海南",
  hebei: "河北",
  heilongjiang: "黑龙江",
  henan: "河南",
  hong_kong: "香港",
  hubei: "湖北",
  hunan: "湖南",
  Inner_Mongolia: "内蒙古",
  jiangsu: "江苏",
  jiangxi: "江西",
  jilin: "吉林",
  liaoning: "辽宁",
  macao: "澳门",
  ningxia: "宁夏",
  qinghai: "青海",
  shaanxi: "陕西",
  shandong: "山东",
  shanghai: "上海",
  shanxi: "山西",
  sichuan: "四川",
  taiwan: "台湾",
  tianjin: "天津",
  xinjiang: "新疆",
  xizang: "西藏",
  yunnan: "云南",
  zhejiang: "浙江"
};

export const normalizeProvinceName = (name = "") =>
  String(name)
    .replace("新疆维吾尔自治区", "新疆")
    .replace("广西壮族自治区", "广西")
    .replace("宁夏回族自治区", "宁夏")
    .replace("西藏自治区", "西藏")
    .replace("内蒙古自治区", "内蒙古")
    .replace("香港特别行政区", "香港")
    .replace("澳门特别行政区", "澳门")
    .replace(/[省市]/g, "");
