/* Used by both customer pages and the admin publication preview. */
window.publishedProfile = function(fields, english=false) {
  const labels={
    headquarters:["总部","Headquarters"],website:["官网","Website"],founded_date:["成立日期","Founded"],
    founders:["创始人","Founders"],founder_education:["创始人学历","Founders’ education"],
    founder_work_background:["创始人经历","Founders’ experience"],business_description:["主营业务","Business overview"],
    products:["产品","Products"],primary_tracks:["一级赛道","Sectors"],sub_tracks:["细分赛道","Subsectors"],
    technology_routes:["技术路线","Technical approaches"],application_scenarios:["应用场景","Use cases"],
    funding_stage:["融资阶段","Funding stage"],funding_history:["融资历史","Funding history"],
    historical_investors:["历史投资方","Investors"],valuation:["估值","Valuation"],major_customers:["客户","Customers"],
    business_models:["商业模式","Business models"],shipments:["出货量","Shipments"],revenue:["营收","Revenue"],
    employee_scale:["员工规模","Headcount"],contact_information:["公开联系方式","Public contact details"]};
  const list=document.createElement("dl");
  for(const [key,value] of Object.entries(fields||{})){
    if(value==null||value===""||Array.isArray(value)&&!value.length)continue;
    const title=document.createElement("dt"),item=document.createElement("dd");
    title.textContent=labels[key]?.[Number(english)]||key;
    item.textContent=Array.isArray(value)?value.join(" · "):typeof value==="object"?value.value||JSON.stringify(value):value;
    list.append(title,item);
  }
  return list;
};
