// Asryto experimental native worker. Same qwentts ABI, model and full ICL.
// Independently implemented; no Lunar source is incorporated.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <mmsystem.h>
#include <mmreg.h>
#include <psapi.h>
#include <bcrypt.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <vector>
#include <string>
#include <list>
#include <chrono>
#include <cmath>
#include <codecvt>
#include <locale>
#include <iomanip>
#include <sstream>
#include <cstring>
#include <cstdlib>
#include "json.hpp"
#include "qwen.h"
using J=nlohmann::json;namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;
static auto boot=Clock::now();
static int ms(Clock::time_point a){return (int)std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now()-a).count();}
static void environment(const char* name,const char* value){if(_putenv_s(name,value?value:"")!=0)throw std::runtime_error("Environment update failed");if(!SetEnvironmentVariableA(name,value))throw std::runtime_error("Process environment update failed");}
static std::string read(const fs::path& p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("File unavailable");return {std::istreambuf_iterator<char>(f),{}};}
static std::string sha_stream(std::istream& input){
 BCRYPT_ALG_HANDLE a{};BCRYPT_HASH_HANDLE h{};std::vector<unsigned char> buf(1024*1024),obj;unsigned char digest[32];DWORD count=0,size=0;
 if(BCryptOpenAlgorithmProvider(&a,BCRYPT_SHA256_ALGORITHM,nullptr,0)<0)throw std::runtime_error("SHA provider failed");
 if(BCryptGetProperty(a,BCRYPT_OBJECT_LENGTH,(PUCHAR)&size,sizeof(size),&count,0)<0){BCryptCloseAlgorithmProvider(a,0);throw std::runtime_error("SHA size failed");}obj.resize(size);
 if(BCryptCreateHash(a,&h,obj.data(),size,nullptr,0,0)<0){BCryptCloseAlgorithmProvider(a,0);throw std::runtime_error("SHA init failed");}
 while(input){input.read((char*)buf.data(),buf.size());auto n=input.gcount();if(n&&BCryptHashData(h,buf.data(),(ULONG)n,0)<0){BCryptDestroyHash(h);BCryptCloseAlgorithmProvider(a,0);throw std::runtime_error("SHA update failed");}}
 auto status=BCryptFinishHash(h,digest,32,0);BCryptDestroyHash(h);BCryptCloseAlgorithmProvider(a,0);if(status<0)throw std::runtime_error("SHA finish failed");
 std::ostringstream s;for(auto b:digest)s<<std::hex<<std::setw(2)<<std::setfill('0')<<(int)b;return s.str();
}
static std::string sha_file(const fs::path& p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("Hash file unavailable");return sha_stream(f);}
static std::string sha_text(const std::string& s){std::istringstream in(s);return sha_stream(in);}
static J mem(){PROCESS_MEMORY_COUNTERS_EX m{};m.cb=sizeof(m);if(!GetProcessMemoryInfo(GetCurrentProcess(),(PROCESS_MEMORY_COUNTERS*)&m,sizeof(m)))return nullptr;return {{"residentMiB",m.WorkingSetSize/1048576.0},{"privateMiB",m.PrivateUsage/1048576.0},{"peakResidentMiB",m.PeakWorkingSetSize/1048576.0}};}
static void emit(J j){j["processMemory"]=mem();std::cout<<"@@COSY@@"<<j.dump()<<std::endl;}
static void stage(const char* name,const char* detail){emit({{"type","status"},{"stage",name},{"detail",detail}});}
struct Device{int index;std::string name,kind;uint32_t vendor;};
static std::vector<Device> devices(){
 HMODULE dll=LoadLibraryW(L"vulkan-1.dll");if(!dll)throw std::runtime_error("Vulkan driver unavailable");
 struct Create{uint32_t type;const void* next;uint32_t flags;const void* app;uint32_t nl;const void* layers;uint32_t ne;const void* extensions;};
 using CreateFn=int(__stdcall*)(const Create*,const void*,void**);using EnumFn=int(__stdcall*)(void*,uint32_t*,void*);using PropFn=void(__stdcall*)(void*,void*);using DestroyFn=void(__stdcall*)(void*,void*);
 auto create=(CreateFn)GetProcAddress(dll,"vkCreateInstance");auto list=(EnumFn)GetProcAddress(dll,"vkEnumeratePhysicalDevices");auto prop=(PropFn)GetProcAddress(dll,"vkGetPhysicalDeviceProperties");auto destroy=(DestroyFn)GetProcAddress(dll,"vkDestroyInstance");
 if(!create||!list||!prop||!destroy){FreeLibrary(dll);throw std::runtime_error("Vulkan symbols unavailable");}
 Create c{};c.type=1;void* instance=nullptr;if(create(&c,nullptr,&instance)){FreeLibrary(dll);throw std::runtime_error("Vulkan instance failed");}
 std::vector<Device> out;
 try{uint32_t n=0;if(list(instance,&n,nullptr))throw std::runtime_error("Vulkan enumeration failed");std::vector<void*> raw(n);if(list(instance,&n,raw.data()))throw std::runtime_error("Vulkan inventory changed");for(uint32_t i=0;i<n;i++){alignas(8) unsigned char b[4096]{};prop(raw[i],b);uint32_t kind,vendor;memcpy(&vendor,b+8,4);memcpy(&kind,b+16,4);if(kind==1||kind==2)out.push_back({(int)i,std::string((char*)b+20),kind==1?"integrated":"discrete",vendor});}}
 catch(...){destroy(instance,nullptr);FreeLibrary(dll);throw;}destroy(instance,nullptr);FreeLibrary(dll);return out;
}
static std::vector<std::string> pieces(const std::string& text){
 std::wstring_convert<std::codecvt_utf8<char32_t>,char32_t> cv;auto s=cv.from_bytes(text);std::vector<std::u32string> sentences,parts;std::u32string sentence,current;
 for(char32_t c:s){sentence+=c;if(std::u32string(U"。！？!?；;").find(c)!=std::u32string::npos){sentences.push_back(sentence);sentence.clear();}}if(!sentence.empty())sentences.push_back(sentence);
 for(auto value:sentences){if(current.size()+value.size()>32&&!current.empty()){parts.push_back(current);current.clear();}while(value.size()>32){size_t cut=32;int best=1000;for(size_t i=0;i<32;i++){size_t end=i+1;bool boundary=std::u32string(U"，,：:。！？!?；;").find(value[i])!=std::u32string::npos;if(value[i]==U'—'&&i+1<32&&value[i+1]==U'—'){end=i+2;boundary=true;i++;}else if(value[i]==U'…'&&i+1<32&&value[i+1]==U'…'){while(i+1<32&&value[i+1]==U'…')i++;end=i+1;boundary=true;}if(boundary&&end>=12){int delta=std::abs((int)end-24);if(delta<best||(delta==best&&end>cut)){cut=end;best=delta;}}}parts.push_back(value.substr(0,cut));value.erase(0,cut);}current+=value;}if(!current.empty())parts.push_back(current);
 std::vector<std::string> out;for(const auto& v:parts){bool content=false;for(auto c:v){bool space=(c>=9&&c<=13)||(c>=0x1c&&c<=0x20)||c==0x85||c==0xa0||c==0x1680||(c>=0x2000&&c<=0x200a)||c==0x2028||c==0x2029||c==0x202f||c==0x205f||c==0x3000;if(!space){content=true;break;}}if(content)out.push_back(cv.to_bytes(v));}return out;
}
struct Engine {
 HMODULE dll{};qt_context* ctx{};J cfg,native;fs::path root;Device device{};std::vector<float> embedding;std::vector<int32_t> codes;int frames{};std::string refText;
#define FN(name) decltype(&name) name##_fn{}
 FN(qt_init_default_params);FN(qt_init);FN(qt_free);FN(qt_tts_default_params);FN(qt_synthesize);FN(qt_audio_free);FN(qt_version);FN(qt_last_error);
 int (*qt_adaptive_kv_state_fn)(qt_context*,int*,int*,uint64_t*){};
#undef FN
 Engine(fs::path r,std::string selected):root(r){
  cfg=J::parse(read(root/"native-runtime.json"));if(!cfg.contains("speechOnly")||cfg["speechOnly"].value("format",0)!=1)throw std::runtime_error("Trial supports verified speech-only profile only");
  if(!cfg.value("adaptiveKv",false)||!cfg.value("compactGraphs",false)||!cfg.value("streamTextEmbedding",false)||cfg.value("kvContext",0)!=1024)throw std::runtime_error("Trial requires the verified progressive-KV text-row profile");
  stage("validate_model","Validating exact native model and voice");
  for(auto k:{"dll","model","codec"}){std::string expected=std::string(k)=="dll"?cfg["dllSha256"].get<std::string>():cfg["speechOnly"]["hashes"][k].get<std::string>();if(sha_file(fs::u8path(cfg[k].get<std::string>()))!=expected)throw std::runtime_error("Runtime SHA mismatch");}
  auto feature=root/"voice-features.json";if(sha_file(feature)!=cfg["speechOnly"]["featuresSha256"])throw std::runtime_error("Voice SHA mismatch");auto doc=J::parse(read(feature));std::string raw=doc["payload"];if(sha_text(raw)!=doc["sha256"])throw std::runtime_error("Feature payload SHA mismatch");auto f=J::parse(raw);embedding=f["embedding"].get<std::vector<float>>();codes=f["codes"].get<std::vector<int32_t>>();frames=f["frames"];
  if(embedding.size()!=1024||frames<1||frames>187||codes.size()!=16*(size_t)frames)throw std::runtime_error("Invalid full ICL reference");for(auto x:embedding)if(!std::isfinite(x))throw std::runtime_error("Invalid embedding");for(auto x:codes)if(x<0||x>=2048)throw std::runtime_error("Invalid reference codes");
  auto v=devices();if(selected.empty())selected=cfg.value("deviceName",std::string());int matches=0;for(auto d:v)if(d.name==selected){device=d;matches++;}if(matches!=1)throw std::runtime_error("Explicit GPU missing or ambiguous; no fallback");
  native={{"adaptiveKv",cfg.value("adaptiveKv",false)},{"compactGraphs",cfg.value("compactGraphs",false)},{"streamTextEmbedding",cfg.value("streamTextEmbedding",false)},{"cpuThreads",4},{"kvContext",cfg.value("kvContext",1024)},{"kvPrecision","FP32"},{"memoryPolicy",device.kind=="discrete"&&device.vendor==0x10de?"device-local":"backend-default"}};
  environment("GGML_BACKEND","Vulkan0");environment("GGML_VK_VISIBLE_DEVICES",std::to_string(device.index).c_str());environment("QWEN_CPU_THREADS","4");environment("QWEN_TTS_KV_CONTEXT",std::to_string(cfg.value("kvContext",1024)).c_str());
  for(auto pair:{std::pair{"compactGraphs","QWEN_TTS_COMPACT_GRAPHS"},{"streamTextEmbedding","QWEN_TTS_STREAM_TEXT_EMBEDDING"},{"adaptiveKv","QWEN_TTS_ADAPTIVE_KV"}})environment(pair.second,cfg.value(pair.first,false)?"1":nullptr);
  if(device.kind=="discrete"&&device.vendor==0x10de){environment("GGML_VK_DISABLE_HOST_VISIBLE_VIDMEM","1");environment("GGML_VK_PREFER_HOST_MEMORY",nullptr);environment("GGML_VK_ALLOW_SYSMEM_FALLBACK",nullptr);}
  SetPriorityClass(GetCurrentProcess(),BELOW_NORMAL_PRIORITY_CLASS);
  auto p=fs::u8path(cfg["dll"].get<std::string>());SetDllDirectoryW(p.parent_path().c_str());dll=LoadLibraryExW(p.c_str(),nullptr,LOAD_WITH_ALTERED_SEARCH_PATH);if(!dll)throw std::runtime_error("Native library load failed");
#define LOAD(name) name##_fn=(decltype(name##_fn))GetProcAddress(dll,#name);if(!name##_fn)throw std::runtime_error("Missing native symbol " #name)
  LOAD(qt_init_default_params);LOAD(qt_init);LOAD(qt_free);LOAD(qt_tts_default_params);LOAD(qt_synthesize);LOAD(qt_audio_free);LOAD(qt_version);LOAD(qt_last_error);LOAD(qt_adaptive_kv_state);
#undef LOAD
  if(std::string(qt_version_fn()).find("51512f1 ")!=0)throw std::runtime_error("Unverified ABI revision");
 }
 ~Engine(){close();if(dll)FreeLibrary(dll);}
 void close(){if(ctx){qt_free_fn(ctx);ctx=nullptr;}}
 void load(){
  MEMORYSTATUSEX m{};m.dwLength=sizeof(m);double minimum=device.kind=="discrete"&&device.vendor==0x10de&&cfg.value("adaptiveKv",false)?2.75:3.0;if(!GlobalMemoryStatusEx(&m)||m.ullAvailPhys<minimum*1073741824.0)throw std::runtime_error("Native trial free RAM below existing protection line");
  stage("load_model","Loading exact approved full-ICL speech model");qt_init_params p{};qt_init_default_params_fn(&p);if(p.abi_version!=5)throw std::runtime_error("Unexpected ABI");auto a=cfg["model"].get<std::string>(),b=cfg["codec"].get<std::string>();p.talker_path=a.c_str();p.codec_path=b.c_str();p.max_batch=1;p.use_fa=false;ctx=qt_init_fn(&p);if(!ctx)throw std::runtime_error(qt_last_error_fn());
  int capacity=0,limit=0;uint64_t bytes=0;if(!qt_adaptive_kv_state_fn(ctx,&capacity,&limit,&bytes)||capacity!=256||limit!=1024)throw std::runtime_error("Native environment/layout did not activate; refusing benchmark");native["kvCapacity"]=capacity;native["kvAllocatedMiB"]=bytes/1048576.0;
 }
 struct Collect{std::vector<float> samples;Clock::time_point started=Clock::now();bool invalid=false;};
 static bool cancel(void* data){return ms(((Collect*)data)->started)>60000;}
 static bool chunk(const float* samples,int n,void* data){auto& c=*(Collect*)data;if(n<0||c.samples.size()+(size_t)n>360*1920){c.invalid=true;return false;}for(int i=0;i<n;i++)if(!std::isfinite(samples[i])){c.invalid=true;return false;}try{c.samples.insert(c.samples.end(),samples,samples+n);return true;}catch(...){c.invalid=true;return false;}}
 std::vector<float> synth(const std::string& text){
  if(!ctx)throw std::runtime_error("Model is asleep");qt_tts_params p{};qt_tts_default_params_fn(&p);p.text=text.c_str();p.lang="Chinese";p.ref_text=refText.c_str();p.speaker=nullptr;p.ref_spk_emb=embedding.data();p.ref_spk_dim=1024;p.ref_codes=codes.data();p.ref_T=frames;p.seed=44;p.max_new_tokens=360;p.temperature=.9f;p.top_k=50;p.top_p=1;p.repetition_penalty=1.05f;p.subtalker_temperature=.9f;p.subtalker_top_k=50;p.subtalker_top_p=1;
  Collect c;p.cancel=cancel;p.cancel_user_data=&c;p.on_chunk=chunk;p.on_chunk_user_data=&c;qt_audio out{};int status=qt_synthesize_fn(ctx,&p,&out);qt_audio_free_fn(&out);if(status||c.invalid)throw std::runtime_error(qt_last_error_fn());if(c.samples.empty()||c.samples.size()>=360*1920)throw std::runtime_error("Incomplete or empty audio");return std::move(c.samples);
 }
};
static void play(std::vector<float>& data,double volume){
 if(volume==0)return;for(float& sample:data)sample*=(float)(volume/100);
 WAVEFORMATEX fmt{};fmt.wFormatTag=WAVE_FORMAT_IEEE_FLOAT;fmt.nChannels=1;fmt.nSamplesPerSec=24000;fmt.wBitsPerSample=32;fmt.nBlockAlign=4;fmt.nAvgBytesPerSec=96000;
 HANDLE event=CreateEventW(nullptr,FALSE,FALSE,nullptr);HWAVEOUT out{};if(!event||waveOutOpen(&out,WAVE_MAPPER,&fmt,(DWORD_PTR)event,0,CALLBACK_EVENT)!=MMSYSERR_NOERROR){if(event)CloseHandle(event);throw std::runtime_error("Audio output unavailable");}
 WAVEHDR header{};header.lpData=(LPSTR)data.data();header.dwBufferLength=(DWORD)(data.size()*4);auto prepared=waveOutPrepareHeader(out,&header,sizeof(header));auto written=prepared==MMSYSERR_NOERROR?waveOutWrite(out,&header,sizeof(header)):MMSYSERR_ERROR;
 if(written==MMSYSERR_NOERROR){while(!(header.dwFlags&WHDR_DONE)){if(WaitForSingleObject(event,90000)!=WAIT_OBJECT_0){waveOutReset(out);written=MMSYSERR_ERROR;break;}}}
 waveOutUnprepareHeader(out,&header,sizeof(header));waveOutClose(out);CloseHandle(event);if(written!=MMSYSERR_NOERROR)throw std::runtime_error("Audio playback failed");
}
int main(int argc,char** argv){
 SetConsoleOutputCP(CP_UTF8);SetConsoleCP(CP_UTF8);
 if(argc==2&&std::string(argv[1])=="--about"){std::cout<<J({{"experimental",true},{"worker","native-cpp"},{"defaultAdopted",false},{"mode","buffered-only"}}).dump()<<std::endl;return 0;}
 if(argc==2&&std::string(argv[1])=="--split-test"){std::string line;while(std::getline(std::cin,line)){try{std::cout<<J(pieces(J::parse(line).get<std::string>())).dump()<<std::endl;}catch(...){return 1;}}return 0;}
std::string id;fs::path root,capture;std::string device,reference;bool silent=false;
 try{
  for(int i=1;i<argc;i++){std::string k=argv[i];if(k=="--no-play")silent=true;else if(i+1<argc){auto value=argv[++i];if(k=="--runtime")root=fs::u8path(value);else if(k=="--device-name")device=value;else if(k=="--reference-text")reference=read(fs::u8path(value));else if(k=="--capture")capture=fs::u8path(value);else throw std::runtime_error("Unknown argument");}else throw std::runtime_error("Missing argument");}
  if(!reference.empty()&&sha_text(reference)!="dca3156a1b5b2397c2c57a8aefd10af61be008276e6b56c10a39b4f84ed04034")throw std::runtime_error("Reference transcript does not match approved voice");
  if(root.empty()||reference.empty())throw std::runtime_error("Runtime and reference text file required");
  Engine engine(root,device);engine.refText=reference;engine.load();auto ready=[&](){emit({{"type","ready"},{"engineVersion","0.6.0-experimental"},{"device",engine.device.name},{"deviceType",engine.device.kind},{"sampleRate",24000},{"nativeSettings",engine.native},{"startupTimings",{{"totalMs",ms(boot)}}},{"workerKind","native-cpp-trial"}});};ready();
  std::string line;for(;;){if(!std::getline(std::cin,line))break;if(line.size()>65536)throw std::runtime_error("Request exceeds limits");try{
   J request=J::parse(line);auto type=request.value("type",std::string());if(type=="quit")break;if(type=="sleep"){engine.close();emit({{"type","slept"}});continue;}if(type=="wake"){if(!engine.ctx)engine.load();ready();continue;}
   id=request.value("id",std::string());if(id.empty()||id.size()>80||id.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")!=std::string::npos)throw std::runtime_error("Invalid id");
   std::string text=request.value("text",std::string());double volume=request.value("volume",65.0);if(!std::isfinite(volume)||volume<0||volume>100||request.value("speed",1.0)!=1)throw std::runtime_error("Invalid volume or speed");if(request.contains("referenceAudio"))throw std::runtime_error("Reference replacement forbidden");
   auto started=Clock::now();std::vector<float> audio;auto list=pieces(text);stage("synthesizing","Generating exact approved voice");
   for(const auto& piece:list){auto a=engine.synth(piece);if(audio.size()+a.size()>24000*180)throw std::runtime_error("Utterance exceeds bounded audio limit");audio.insert(audio.end(),a.begin(),a.end());}
   int synthesis=ms(started);auto hash=sha_text(std::string((char*)audio.data(),audio.size()*4));if(!capture.empty()){fs::create_directories(capture);std::ofstream out(capture/(id+".f32"),std::ios::binary);out.write((char*)audio.data(),audio.size()*4);if(!out)throw std::runtime_error("Capture failed");}
   emit({{"type","status"},{"stage","playing"},{"id",id},{"synthesisMs",synthesis},{"detail",silent?"Verification only; no audio output":"Native buffered playback"}});double seconds=audio.size()/24000.0;if(!silent)play(audio,volume);
   emit({{"type","done"},{"id",id},{"seconds",seconds},{"totalSynthesisMs",synthesis},{"firstChunkMs",synthesis},{"realTimeFactor",seconds?synthesis/1000.0/seconds:0},{"pcmSha256",hash},{"pieceCount",list.size()},{"effectivePlaybackMode","buffered"},{"workerKind","native-cpp-trial"},{"playbackVerified",!silent}});
  }catch(const std::exception& e){emit({{"type","error"},{"id",id},{"error",e.what()}});}}
 }catch(const std::exception& e){emit({{"type","error"},{"stage","initialization"},{"error",e.what()}});return 1;}return 0;
}
