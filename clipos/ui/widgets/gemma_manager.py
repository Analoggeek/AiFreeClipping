"""Native Gemma management; all potentially blocking calls live off the UI thread."""
from PySide6.QtCore import QThread,Signal
from PySide6.QtWidgets import QLabel,QComboBox,QPushButton,QHBoxLayout,QGridLayout,QMessageBox,QProgressBar
from .common import Card,SectionHeader,format_size
from ...ai.gemma_runtime import GemmaRuntime,GEMMA_TAGS,DEFAULT_MODEL,PROFILES

class RuntimeJob(QThread):
    result=Signal(object)
    error=Signal(str)
    status=Signal(str)
    def __init__(self,fn,parent):super().__init__(parent);self.fn=fn
    def run(self):
        try:self.result.emit(self.fn(self))
        except Exception as exc:self.error.emit(str(exc))

class GemmaManager(Card):
    def __init__(self,window):
        super().__init__();self.window=window;self.db=window.db;self.worker=None
        self.add(SectionHeader('Gemma · Local AI Director','Ollama manages local weights. Downloads require approval; installed models work offline.'))
        self.model=QComboBox();self.model.setEditable(True);self.model.addItems(GEMMA_TAGS)
        self.model.setCurrentText(self.db.get_setting('llm_model',DEFAULT_MODEL));self.add(self.model)
        self.profile=QComboBox();self.profile.addItems(PROFILES)
        self.profile.setCurrentText(self.db.get_setting('director_profile','Balanced'))
        self.profile.setToolTip('Director context/output budgets only. CPU/Metal/CUDA placement is managed and reported by Ollama, not assumed by CLIPOS.')
        self.profile.currentTextChanged.connect(lambda text:self.db.set_setting('director_profile',text));self.add(self.profile)
        self.info=QLabel('Not checked. Install/start Ollama on this device, then refresh.');self.info.setWordWrap(True);self.add(self.info)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.hide();self.add(self.progress)
        row=QGridLayout();self.buttons=[]
        for text,fn in [('Refresh installed',self.check),('Download Gemma…',self.download),('Test offline inference',self.test),('Unload weights',self.unload),('Loaded memory',self.memory)]:
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b,len(self.buttons)//3,len(self.buttons)%3);self.buttons.append(b)
        self.add_layout(row)
        b=QPushButton('Use selected model for editing');b.clicked.connect(self.select);self.add(b);self.buttons.append(b)
        self.add(QLabel('Install Ollama separately from ollama.com; then start it locally. Model logs are managed by Ollama.'))
        self.add(QLabel('No automatic downloads. Unload releases model memory, not the Ollama service.'))
    def runtime(self):
        try:return GemmaRuntime(self.db.get_setting('ollama_host','http://127.0.0.1:11434'))
        except Exception as exc:self.info.setText(str(exc));return None
    def launch(self,fn,done):
        if self.worker and self.worker.isRunning():return
        for b in self.buttons:b.setEnabled(False)
        self.model.setEnabled(False);self.progress.show()
        self.worker=RuntimeJob(fn,self)
        self.worker.result.connect(done);self.worker.error.connect(self.info.setText);self.worker.status.connect(self.info.setText)
        self.worker.finished.connect(self.finished);self.worker.start()
    def finished(self):
        for b in self.buttons:b.setEnabled(True)
        self.model.setEnabled(True);self.progress.hide()
    def check(self):
        runtime=self.runtime()
        if runtime is None:return
        self.launch(lambda _:runtime.status(),lambda rows:self.info.setText('Installed local models: '+(', '.join(x['name']+' · '+format_size(x['size']) for x in rows) or 'none. Download explicitly first.')))
    def memory(self):
        runtime=self.runtime()
        if runtime is None:return
        self.launch(lambda _:runtime.memory(),lambda rows:self.info.setText('Ollama loaded weights: '+(', '.join(x['name']+' '+format_size(x['size'])+'; GPU allocation '+format_size(x['vram']) for x in rows) or 'none. GPU allocation is not whole-system GPU utilization.')))
    def download(self):
        model=self.model.currentText().strip()
        if model not in GEMMA_TAGS:self.info.setText('Select a verified Gemma download tag. Alternative installed models can still be selected.');return
        if QMessageBox.question(self,'Download local weights?',f'Allow a one-time internet download of {model} through local Ollama (including when editing offline mode is on)? This may require several GB of disk/RAM. Gemma terms apply. No media is uploaded.')!=QMessageBox.StandardButton.Yes:return
        runtime=self.runtime()
        if runtime is None:return
        self.launch(lambda job:runtime.pull(model,consent=True,cancelled=job.isInterruptionRequested,progress=lambda x:job.status.emit(str(x.get('status','Downloading'))+' '+str(x.get('completed',''))+'/'+str(x.get('total','')))),lambda _:self.info.setText(model+' downloaded and verified as local GGUF weights.'))
    def test(self):
        runtime=self.runtime();model=self.model.currentText().strip()
        if runtime is None:return
        self.launch(lambda _:runtime.verify_offline(model),self.info.setText)
    def unload(self):
        runtime=self.runtime();model=self.model.currentText().strip()
        if runtime is None:return
        self.launch(lambda _:runtime.unload(model),lambda _:self.info.setText('Model unload requested. Ollama service remains running.'))
    def select(self):
        runtime=self.runtime();model=self.model.currentText().strip()
        if runtime is None:return
        def done(_):
            self.db.set_setting('llm_model',model);self.window.settings_changed.emit();self.info.setText(model+' selected; local weights verified.')
        self.launch(lambda _:runtime.client.require_local_model(model),done)
    def shutdown(self):
        # Keep the owning window alive until its request completes; never destroy
        # a running QThread. Requests are bounded by the transport timeout.
        if self.worker and self.worker.isRunning():self.worker.requestInterruption();self.worker.wait()
